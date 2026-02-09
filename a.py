from utils import (
    parse_cookie_string,
    generate_offline_threading_id,
    generate_session_id,
    generate_client_id,
    json_minimal,
    gen_threading_id,
    get_headers,
    formAll,
    mainRequests,
    dataGetHome,
)
import json
import random
import paho.mqtt.client as mqtt
from urllib.parse import urlparse
import ssl
import requests
import time
import os
def cls():
    os.system('cls' if os.name == 'nt' else 'clear')

def getUserName(dataFB, userID):
    try:
        dataForm = formAll(dataFB, requireGraphql=False)
        dataForm["ids[0]"] = userID
        req = mainRequests(
            "https://www.facebook.com/chat/user_info/",
            dataForm,
            dataFB["cookieFacebook"]
        )
        resp = requests.post(**req)
        jsonData = json.loads(resp.text.split("for (;;);")[1])["payload"]["profiles"][str(userID)]
        return jsonData.get("name", "Unknown")
    except Exception:
        return "Unknown"

def get_guid():
    return generate_client_id()

def format_id(id_str):
    return str(id_str)

class FacebookMQTTSender:
    def __init__(self, cookies: str, account_name: str = ""):
        self.cookies = cookies
        self.account_name = account_name
        self.dataFB = dataGetHome(cookies)
        self.user_id = self._extract_user_id()
        self.mqtt_client = None
        self.connected = False
        self.ws_task_number = 0
        self.ws_req_number = 0
        self.last_seq_id = None
        self.box_seq_ids = {}  # Lưu seq_id cho từng box riêng biệt
        self.queues_created = {}  # Lưu các queue đã tạo cho từng box
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36"

    def _extract_user_id(self):
        cookie_dict = parse_cookie_string(self.cookies)
        user_id = cookie_dict.get("c_user")
        if not user_id:
            raise ValueError("Invalid cookies: c_user not found")
        return user_id

    def _get_seq_id_for_box(self, thread_id: str):
        """Lấy sequence ID cho một box cụ thể"""
        form = formAll(self.dataFB, "CometChatInboxQuery", "3336396659757871")
        form["queries"] = json_minimal({
            "o0": {
                "doc_id": "3336396659757871",
                "query_params": {
                    "limit": 1,
                    "before": None,
                    "tags": ["INBOX"],
                    "includeDeliveryReceipts": False,
                    "includeSeqID": True,
                    "threadID": thread_id
                }
            }
        })
        
        req_params = mainRequests(
            "https://www.facebook.com/api/graphqlbatch/",
            form,
            self.cookies
        )
        
        try:
            res = requests.post(**req_params)
            response_text = res.text
            if response_text.startswith("for(;;);"):
                response_text = response_text[9:]
            response_parts = response_text.split("\n")
            first_part = response_parts[0]
            if first_part.strip():
                response_data = json.loads(first_part)
                if ("o0" in response_data and
                    "data" in response_data["o0"] and
                    "viewer" in response_data["o0"]["data"] and
                    "message_threads" in response_data["o0"]["data"]["viewer"]):
                    seq_id = response_data["o0"]["data"]["viewer"]["message_threads"]["sync_sequence_id"]
                    self.box_seq_ids[thread_id] = seq_id
                    return seq_id
                else:
                    raise Exception("Could not find sync_sequence_id in response")
            else:
                raise Exception("Empty response from Facebook")
        except Exception as e:
            return self.last_seq_id

    def _get_seq_id(self):
        form = formAll(self.dataFB, "CometChatInboxQuery", "3336396659757871")
        form["queries"] = json_minimal({
            "o0": {
                "doc_id": "3336396659757871",
                "query_params": {
                    "limit": 1,
                    "before": None,
                    "tags": ["INBOX"],
                    "includeDeliveryReceipts": False,
                    "includeSeqID": True
                }
            }
        })
        
        req_params = mainRequests(
            "https://www.facebook.com/api/graphqlbatch/",
            form,
            self.cookies
        )
        
        try:
            res = requests.post(**req_params)
            response_text = res.text
            if response_text.startswith("for(;;);"):
                response_text = response_text[9:]
            response_parts = response_text.split("\n")
            first_part = response_parts[0]
            if first_part.strip():
                response_data = json.loads(first_part)
                if ("o0" in response_data and
                    "data" in response_data["o0"] and
                    "viewer" in response_data["o0"]["data"] and
                    "message_threads" in response_data["o0"]["data"]["viewer"]):
                    self.last_seq_id = response_data["o0"]["data"]["viewer"]["message_threads"]["sync_sequence_id"]
                else:
                    raise Exception("Could not find sync_sequence_id in response")
            else:
                raise Exception("Empty response from Facebook")
        except Exception as e:
            raise Exception(f"Failed to get sequence ID: {str(e)}")

    def connect(self, box_ids=None):
        """
        Kết nối MQTT
        box_ids: danh sách các box ID cần lấy seq_id riêng
        """
        if self.connected:
            return
        
        # Lấy seq_id chung trước
        self._get_seq_id()
        
        # Nếu có danh sách box_ids, lấy seq_id cho từng box
        if box_ids:
            for box_id in box_ids:
                self._get_seq_id_for_box(box_id)
                time.sleep(0.5)  # Delay nhỏ giữa các request
        
        session_id = generate_session_id()
        user = {
            "a": self.user_agent,
            "u": self.user_id,
            "s": session_id,
            "chat_on": True,
            "fg": False,
            "d": get_guid(),
            "ct": "websocket",
            "aid": "2.19994525426954e+14",
            "mqtt_sid": "",
            "cp": 3,
            "ecp": 10,
            "st": [],
            "pm": [],
            "dc": "",
            "no_auto_fg": True,
            "gas": None,
            "pack": [],
        }
        host = f"wss://edge-chat.facebook.com/chat?sid={session_id}&cid={get_guid()}"
        cookie_dict = parse_cookie_string(self.cookies)
        cookie_str = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
        client = mqtt.Client(
            client_id=f"mqttwsclient_{self.user_id}_{int(time.time())}",
            clean_session=True,
            protocol=mqtt.MQTTv31,
            transport="websockets",
        )
        client.tls_set(certfile=None, keyfile=None, cert_reqs=ssl.CERT_NONE, tls_version=ssl.PROTOCOL_TLSv1_2)
        client.tls_insecure_set(True)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.username_pw_set(username=json_minimal(user))
        parsed_host = urlparse(host)
        client.ws_set_options(
            path=f"{parsed_host.path}?{parsed_host.query}",
            headers={
                "Cookie": cookie_str,
                "Origin": "https://www.facebook.com",
                "User-Agent": self.user_agent,
                "Referer": "https://www.facebook.com/",
                "Host": "edge-chat.facebook.com",
            },
        )
        self.mqtt_client = client
        client.connect(
            host="edge-chat.facebook.com",
            port=443,
            keepalive=10,
        )
        client.loop_start()
        timeout = 10
        while not self.connected and timeout > 0:
            time.sleep(0.1)
            timeout -= 0.1
        if not self.connected:
            raise Exception("Failed to connect to MQTT within timeout")

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected = True
            client.publish(
                topic="/ls_app_settings",
                payload=json_minimal({
                    "ls_fdid": "", 
                    "ls_sv": "6928813347213944"
                }),
                qos=1,
                retain=False,
            )
            
            # Chỉ tạo queue cho các box chưa có queue
            if self.box_seq_ids:
                for box_id, seq_id in self.box_seq_ids.items():
                    # Kiểm tra xem queue cho box này đã được tạo chưa
                    if box_id not in self.queues_created:
                        queue = {
                            "sync_api_version": 10,
                            "max_deltas_able_to_process": 1000,
                            "delta_batch_size": 500,
                            "encoding": "JSON",
                            "entity_fbid": self.user_id,
                            "initial_titan_sequence_id": seq_id,  # Dùng seq_id riêng cho từng box
                            "device_params": None
                        }
                        client.publish(
                            topic="/messenger_sync_create_queue",
                            payload=json_minimal(queue),
                            qos=1,
                            retain=False,
                        )
                        # Đánh dấu queue đã được tạo
                        self.queues_created[box_id] = {
                            'queue': queue,
                            'seq_id': seq_id,
                            'created_at': time.time()
                        }
                        time.sleep(0.2)
                    else:
                        pass
            else:
                # Fallback: tạo queue chung nếu không có box_seq_ids
                if 'general' not in self.queues_created:
                    queue = {
                        "sync_api_version": 10,
                        "max_deltas_able_to_process": 1000,
                        "delta_batch_size": 500,
                        "encoding": "JSON",
                        "entity_fbid": self.user_id,
                        "initial_titan_sequence_id": self.last_seq_id,
                        "device_params": None
                    }
                    client.publish(
                        topic="/messenger_sync_create_queue",
                        payload=json_minimal(queue),
                        qos=1,
                        retain=False,
                    )
                    self.queues_created['general'] = {
                        'queue': queue,
                        'seq_id': self.last_seq_id,
                        'created_at': time.time()
                    }

    def _on_disconnect(self, client, userdata, rc):
        self.connected = False

    def send_message(self, text: str, thread_id: str):
        if not self.connected:
            raise ValueError("Not connected to MQTT")
        if not text or not thread_id:
            raise ValueError("text and thread_id are required")
        self.ws_req_number += 1
        self.ws_task_number += 1
        task_payload = {
            "initiating_source": 0,
            "multitab_env": 0,
            "otid": generate_offline_threading_id(),
            "send_type": 1,
            "skip_url_preview_gen": 0,
            "source": 0,
            "sync_group": 1,
            "text": text,
            "text_has_links": 0,
            "thread_id": int(thread_id),
        }
        task = {
            "failure_count": None,
            "label": "46",
            "payload": json.dumps(task_payload, separators=(",", ":")),
            "queue_name": str(thread_id),
            "task_id": self.ws_task_number,
        }
        self.ws_task_number += 1
        task_mark_payload = {
            "last_read_watermark_ts": int(time.time() * 1000),
            "sync_group": 1,
            "thread_id": int(thread_id),
        }
        task_mark = {
            "failure_count": None,
            "label": "21",
            "payload": json.dumps(task_mark_payload, separators=(",", ":")),
            "queue_name": str(thread_id),
            "task_id": self.ws_task_number,
        }
        content = {
            "app_id": "2220391788200892",
            "payload": {
                "data_trace_id": None,
                "epoch_id": int(generate_offline_threading_id()),
                "tasks": [task, task_mark],
                "version_id": "7545284305482586",
            },
            "request_id": self.ws_req_number,
            "type": 3,
        }
        content["payload"] = json.dumps(content["payload"], separators=(",", ":"))
        self.mqtt_client.publish(
            topic="/ls_req",
            payload=json.dumps(content, separators=(",", ":")),
            qos=1,
            retain=False,
        )
        return True

    def disconnect(self):
        if self.mqtt_client and self.connected:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
            self.connected = False
    
    def get_queue_info(self):
        """Lấy thông tin về các queue đã tạo"""
        return {
            'total_queues': len(self.queues_created),
            'queues': self.queues_created
        }


def main():
    try:
        print(r"""
        
 __  __ _       _       ____  _           _   
|  \/  (_)_ __ | |__   |  _ \| |__   __ _| |_ 
| |\/| | | '_ \| '_ \  | |_) | '_ \ / _` | __|
| |  | | | | | | | | | |  __/| | | | (_| | |_ 
|_|  |_|_|_| |_|_| |_| |_|   |_| |_|\__,_|\__|

""")

        
        cookies_list = []
        print("[*] Nhap cookie (go 'done' de ket thuc):")
        count = 1
        while True:
            cookie = input(f"Nhập cookie lần {count}: ").strip()
            if cookie.lower() == "done":
                break
            if not cookie:
                print("Cookie khong duoc de trong!")
                continue
            
            # Lấy tên người dùng từ cookie
            try:
                temp_dataFB = dataGetHome(cookie)
                cookie_dict = parse_cookie_string(cookie)
                user_id = cookie_dict.get("c_user")
                user_name = getUserName(temp_dataFB, user_id)
                
                # Kiểm tra nếu không lấy được tên
                if user_name == "Unknown":
                    print(f"Loi: cookie khong hop le !")
                    continue
                
            except Exception as e:
                print(f"  ✗ Loi: {str(e)}")
                print(f"  --> Cookie khong hop le hoac da het han. Vui long nhap lai.\n")
                continue
            
            cookies_list.append({
                'cookies': cookie,
                'name': user_name
            })
            
            print(f"Da them cookie: {user_name}")
            count += 1

        if not cookies_list:
            print("[!] Chua nhap cookie nao!")
            return

        box_ids_input = input("[+] Nhap cac ID box, cach nhau boi dau phay (,): ").strip()
        box_ids = [box_id.strip() for box_id in box_ids_input.split(",") if box_id.strip()]
        
        if not box_ids:
            print("[!] Chua nhap ID box nao!")
            return

        delay = int(input("[+] Nhap delay giua moi lan gui (giay): "))

        # Hỏi người dùng muốn dùng file riêng hay chung
        use_separate_files = input("[1] > Đa Ngôn\n[2] > Luân Phiên\nNhập Lựa Chọn : ").strip().lower()
        
        box_messages = {}  # Dictionary lưu message cho từng box
        box_files = {}  # Dictionary lưu tên file cho từng box
        
        if use_separate_files == '1':
            for box_id in box_ids:
                while True:
                    message_file = input(f"Ten file cho box {box_id}: ").strip()
                    
                    # Tự động thêm .txt nếu chưa có
                    if not message_file.endswith('.txt'):
                        message_file += '.txt'
                    
                    try:
                        with open(message_file, 'r', encoding='utf-8') as f:
                            message_content = f.read().strip()
                        if not message_content:
                            print(f"File '{message_file}' rong! Vui long nhap lai.")
                            continue
                        box_messages[box_id] = message_content
                        box_files[box_id] = message_file
                        break  # File hợp lệ, thoát vòng lặp
                    except FileNotFoundError:
                        print(f"File '{message_file}' không tồn tại! Vui long nhap lai.")
                        continue
                    except Exception as e:
                        print(f"Loi doc file '{message_file}': {e}. Vui long nhap lai.")
                        continue
            
            if not box_messages:
                print("\n[!] Khong load duoc file nao!")
                return
            
        else:
            while True:
                message_file = input("[+] Nhap ten file chua noi dung tin nhan: ").strip()
                
                # Tự động thêm .txt nếu chưa có
                if not message_file.endswith('.txt'):
                    message_file += '.txt'
                
                try:
                    with open(message_file, 'r', encoding='utf-8') as f:
                        message_content = f.read().strip()
                    if not message_content:
                        print(f"File '{message_file}' rong! Vui long nhap lai.")
                        continue
                    
                    # Gán message chung cho tất cả box
                    for box_id in box_ids:
                        box_messages[box_id] = message_content
                        box_files[box_id] = message_file
                    break  # File hợp lệ, thoát vòng lặp
                        
                except FileNotFoundError:
                    print(f"File '{message_file}' không tồn tại! Vui long nhap lai.")
                    continue
                except Exception as e:
                    print(f"Loi doc file '{message_file}': {e}. Vui long nhap lai.")
                    continue

        # Dictionary để lưu sender cho mỗi account
        senders = {}
        total_spam_count = 0  # Đếm tổng số lần gửi tin nhắn (không phân biệt box)
        
        current_acc_index = 0
        
        while True:
            # Lấy account hiện tại
            cookie_data = cookies_list[current_acc_index]
            account_name = cookie_data['name']
            
            try:
                # Kiểm tra xem đã có sender cho account này chưa
                if account_name not in senders:
                    sender = FacebookMQTTSender(cookie_data['cookies'], account_name)
                    sender.connect(box_ids=list(box_messages.keys()))
                    senders[account_name] = sender
                else:
                    sender = senders[account_name]
                
                # Gửi tin nhắn đến tất cả box với account này
                for box_id, message_content in box_messages.items():
                    try:
                        sender.send_message(message_content, box_id)
                        total_spam_count += 1
                        
                        # Log theo format yêu cầu
                        file_name = box_files.get(box_id, "unknown.txt")
                        print(f"[Cookie: {account_name}] BOX: {box_id} | FILE: {file_name} | SPAM LẦN {total_spam_count} THÀNH CÔNG!")
                        
                        # Countdown timer sau mỗi box
                        if delay > 0:
                            for remaining in range(delay, 0, -1):
                                mins = remaining // 60
                                secs = remaining % 60
                                print(f"Vui lòng chờ {mins:02d}:{secs:02d}", end='\r')
                                time.sleep(1)
                            print(" " * 50, end='\r')  # Xóa dòng countdown
                        
                    except Exception as e:
                        print(f"[Cookie: {account_name}] BOX: {box_id} | LỖI: {str(e)[:50]}")
                
                # Clear màn hình sau khi account spam xong tất cả box
                cls()
                time.sleep(3)
                
            except Exception as e:
                print(f"[Cookie: {account_name}] LỖI NGHIÊM TRỌNG: {str(e)}")
                # Nếu lỗi, xóa sender để tạo lại lần sau
                if account_name in senders:
                    try:
                        senders[account_name].disconnect()
                    except:
                        pass
                    del senders[account_name]
                time.sleep(5)
            
            # Chuyển sang account tiếp theo
            current_acc_index = (current_acc_index + 1) % len(cookies_list)

    except KeyboardInterrupt:
        print("\n\n[*] Dang dung chuong trinh...")
        # Disconnect tất cả sender
        for sender in senders.values():
            try:
                sender.disconnect()
            except:
                pass
    except Exception as e:
        print(f"\n[!] Loi: {str(e)}")


if __name__ == "__main__":
    cls()
    main()