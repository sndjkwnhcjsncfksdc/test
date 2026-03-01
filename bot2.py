import json
import os
import time
import random
import threading
import uuid
from pystyle import Colors, Colorate, Center, Write
from zlapi import ZaloAPI
from zlapi.models import *

# ─── helpers ────────────────────────────────────────────────────────────────
mk = lambda: (int(time.time()*1000), uuid.uuid4().hex, uuid.uuid4().hex)
jd = lambda **kw: json.dumps(kw)


class SendLinkBot:
    def __init__(self):
        self.accounts = []
        self.account_boxes = {}
        self.running_threads = {}

    # ── UI ──────────────────────────────────────────────────────────────────
    def clear(self):
        os.system('cls' if os.name == 'nt' else 'clear')

    def banner(self):
        art = """
 ██████╗██████╗  █████╗ ███╗   ███╗    ██╗     ██╗███╗   ██╗██╗  ██╗
██╔════╝██╔══██╗██╔══██╗████╗ ████║    ██║     ██║████╗  ██║██║ ██╔╝
╚█████╗ ██████╔╝███████║██╔████╔██║    ██║     ██║██╔██╗ ██║█████╔╝ 
 ╚═══██╗██╔═══╝ ██╔══██║██║╚██╔╝██║    ██║     ██║██║╚██╗██║██╔═██╗ 
██████╔╝██║     ██║  ██║██║ ╚═╝ ██║    ███████╗██║██║ ╚████║██║  ██╗
╚═════╝ ╚═╝     ╚═╝  ╚═╝╚═╝     ╚═╝    ╚══════╝╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝
        """
        print(Colorate.Horizontal(Colors.rainbow, art))

    def menu(self):
        m = """
 > MENU <

1. Spam Link vào Group
0. Thoát
"""
        print(Colorate.Horizontal(Colors.green_to_blue, m))
        print(Colors.cyan + "-" * 50 + Colors.reset)

    # ── Config / Login ───────────────────────────────────────────────────────
    def load_or_create_configs(self):
        num_accounts = int(input(Colors.yellow + "Bạn muốn dùng bao nhiêu acc: " + Colors.reset).strip())

        existing = []
        for i in range(1, num_accounts + 1):
            f = f"config{i}.json"
            if os.path.exists(f):
                existing.append((i, f))

        if existing:
            print(Colors.yellow + f"[!] Tìm thấy {len(existing)} file config cũ" + Colors.reset)
            for acc_num, fname in existing:
                print(Colors.cyan + f"- {fname}" + Colors.reset)
            choice = input(Colors.cyan + "Dùng config cũ? (y/n): " + Colors.reset).lower().strip()
            if choice == 'y':
                configs = {}
                for acc_num, fname in existing:
                    try:
                        with open(fname, 'r', encoding='utf-8') as fp:
                            configs[acc_num] = json.load(fp)
                    except:
                        print(Colors.red + f"[!] Lỗi đọc {fname}" + Colors.reset)
                        return self.create_configs(num_accounts)
                return configs, num_accounts
            else:
                for acc_num, fname in existing:
                    os.remove(fname)
                print(Colors.green + "[!] Đã xóa config cũ" + Colors.reset)

        return self.create_configs(num_accounts)

    def create_configs(self, num_accounts):
        print(Colors.cyan + f"\n[TẠO CONFIG CHO {num_accounts} TÀI KHOẢN]" + Colors.reset)
        configs = {}
        for i in range(1, num_accounts + 1):
            print(Colors.yellow + f"\n--- Tài khoản {i} ---" + Colors.reset)
            imei = input(Colors.yellow + f"Nhập IMEI {i}: " + Colors.reset).strip()
            cookie_input = input(Colors.yellow + f"Nhập Cookie {i} (JSON): " + Colors.reset).strip()
            try:
                cookie_obj = json.loads(cookie_input)
                if "cookie" in cookie_obj:
                    cookie_data = cookie_obj["cookie"]
                    imei_to_use = cookie_obj.get("imei", imei)
                    phone = cookie_obj.get("phone", f"1101200{i}")
                    password = cookie_obj.get("password", f"Password{i}")
                else:
                    cookie_data = cookie_obj
                    imei_to_use = imei
                    phone = f"1101200{i}"
                    password = f"Password{i}"

                config = {"cookie": cookie_data, "imei": imei_to_use, "phone": phone, "password": password}
                fname = f"config{i}.json"
                with open(fname, 'w', encoding='utf-8') as fp:
                    json.dump(config, fp, ensure_ascii=False, indent=2)

                configs[i] = config
                print(Colors.green + f"[+] Tạo {fname} thành công!" + Colors.reset)
            except json.JSONDecodeError:
                print(Colors.red + f"[!] Cookie {i} không đúng JSON!" + Colors.reset)
                return None, 0
            except Exception as e:
                print(Colors.red + f"[!] Lỗi tạo config {i}: {e}" + Colors.reset)
                return None, 0
        return configs, num_accounts

    def init_accounts(self, configs):
        self.accounts = []
        for acc_num, config in configs.items():
            try:
                api = ZaloAPI(
                    phone=config["phone"],
                    password=config["password"],
                    imei=config["imei"],
                    session_cookies=config["cookie"]
                )
                if api.isLoggedIn():
                    self.accounts.append({'number': acc_num, 'api': api, 'config': config})
                    print(Colors.green + f"[+] Đăng nhập Account {acc_num} thành công!" + Colors.reset)
                else:
                    print(Colors.red + f"[!] Đăng nhập Account {acc_num} thất bại!" + Colors.reset)
            except Exception as e:
                print(Colors.red + f"[!] Lỗi khởi tạo Account {acc_num}: {e}" + Colors.reset)

        if not self.accounts:
            print(Colors.red + "[!] Không có tài khoản nào đăng nhập thành công!" + Colors.reset)
            return False
        print(Colors.green + f"[+] Đã đăng nhập {len(self.accounts)} tài khoản!" + Colors.reset)
        return True

    # ── Fetch Groups ─────────────────────────────────────────────────────────
    def fetch_all_boxes(self, api):
        try:
            all_groups = api.fetchAllGroups()
            box_list = {}
            group_ids = []

            if hasattr(all_groups, 'groupList') and all_groups.groupList:
                for g in all_groups.groupList:
                    if hasattr(g, 'groupId'):
                        group_ids.append(str(g.groupId))
            elif hasattr(all_groups, 'gridVerMap'):
                group_ids = list(all_groups.gridVerMap.keys())
            else:
                if hasattr(all_groups, '__dict__'):
                    for key, value in all_groups.__dict__.items():
                        if isinstance(value, dict):
                            group_ids = list(value.keys())
                            break

            if not group_ids:
                return {}

            batch_size = 10
            for i in range(0, len(group_ids), batch_size):
                batch_ids = group_ids[i:i + batch_size]
                batch_dict = {gid: 0 for gid in batch_ids}
                try:
                    batch_info = api.fetchGroupInfo(batch_dict)
                    self._parse_batch(batch_info, batch_ids, box_list)
                except:
                    for gid in batch_ids:
                        try:
                            info = api.fetchGroupInfo(gid)
                            self._parse_single(info, gid, box_list)
                        except:
                            box_list[gid] = {"name": f"Box {gid}"}
                time.sleep(0.5)

            return box_list
        except Exception as e:
            print(Colors.red + f"[!] Lỗi lấy danh sách box: {e}" + Colors.reset)
            return {}

    def _parse_batch(self, batch_info, group_ids, box_list):
        # gridInfoMap — phổ biến nhất với zlapi
        if hasattr(batch_info, 'gridInfoMap') and batch_info.gridInfoMap:
            for gid, info in batch_info.gridInfoMap.items():
                if gid in group_ids:
                    if isinstance(info, dict):
                        name = info.get('name') or info.get('gn') or info.get('groupName')
                    else:
                        name = getattr(info, 'name', None) or getattr(info, 'gn', None) or getattr(info, 'groupName', None)
                    box_list[gid] = {"name": name or f"Box {gid}"}
        elif hasattr(batch_info, 'mgInfos') and batch_info.mgInfos:
            for gid, info in batch_info.mgInfos.items():
                if gid in group_ids:
                    name = getattr(info, 'gn', None) or getattr(info, 'groupName', None) or f"Box {gid}"
                    box_list[gid] = {"name": name}
        elif hasattr(batch_info, 'groups') and batch_info.groups:
            for g in batch_info.groups:
                if hasattr(g, 'groupId'):
                    gid = str(g.groupId)
                    if gid in group_ids:
                        name = getattr(g, 'groupName', None) or f"Box {gid}"
                        box_list[gid] = {"name": name}
        else:
            for gid in group_ids:
                if gid not in box_list:
                    name = self._extract_name(batch_info, gid)
                    box_list[gid] = {"name": name or f"Box {gid}"}

    def _parse_single(self, info, gid, box_list):
        name = getattr(info, 'groupName', None) or getattr(info, 'gn', None)
        if not name:
            name = self._extract_name(info, gid)
        box_list[gid] = {"name": name or f"Box {gid}"}

    def _extract_name(self, obj, gid):
        for attr in ['groupName', 'gn', 'name', 'title']:
            val = getattr(obj, attr, None)
            if val and isinstance(val, str):
                return val
        if hasattr(obj, '__dict__'):
            for key, value in obj.__dict__.items():
                if ('name' in key.lower() or 'title' in key.lower()) and isinstance(value, str) and value:
                    return value
        return None

    # ── Display / Select Box ─────────────────────────────────────────────────
    def display_boxes(self, box_list, page=0, items_per_page=10):
        if not box_list:
            print(Colors.red + "[!] Không có box nào!" + Colors.reset)
            return False
        items = list(box_list.items())
        total_pages = (len(items) + items_per_page - 1) // items_per_page
        page = max(0, min(page, total_pages - 1))
        start = page * items_per_page
        current = items[start:start + items_per_page]

        print(Colors.cyan + f"\n[DANH SÁCH BOX] - Trang {page + 1}/{total_pages}" + Colors.reset)
        print(Colors.cyan + "-" * 60 + Colors.reset)
        for i, (bid, binfo) in enumerate(current, start=start + 1):
            print(Colors.yellow + f"{i}. {binfo['name']} (ID: {bid})" + Colors.reset)
        print(Colors.cyan + "-" * 60 + Colors.reset)
        print(Colors.green + f"Tổng số box: {len(items)}" + Colors.reset)
        if total_pages > 1:
            print(Colors.blue + "- next: Trang tiếp  |  back: Trang trước" + Colors.reset)
        print(Colors.cyan + "\nChọn box ('done' để xong, 'all' để chọn tất cả)" + Colors.reset)
        return True

    def select_boxes(self, account_number, api):
        box_list = self.fetch_all_boxes(api)
        if not box_list:
            print(Colors.red + f"[!] Account {account_number} không có box nào!" + Colors.reset)
            return []

        selected = []
        page = 0
        items = list(box_list.items())

        while True:
            self.clear()
            self.banner()
            print(Colors.cyan + f"[CHỌN BOX CHO ACCOUNT {account_number}]" + Colors.reset)
            if not self.display_boxes(box_list, page):
                break

            if selected:
                print(Colors.green + f"\n[ĐÃ CHỌN] ({len(selected)} box):" + Colors.reset)
                for i, b in enumerate(selected, 1):
                    print(Colors.yellow + f"{i}. {b['name']} (ID: {b['id']})" + Colors.reset)

            choice = input(Colors.cyan + "\nLựa chọn: " + Colors.reset).strip().lower()

            if choice == 'done':
                break
            elif choice == 'all':
                selected = [{'id': bid, 'name': binfo['name']} for bid, binfo in items]
                print(Colors.green + f"[+] Đã chọn tất cả {len(selected)} box!" + Colors.reset)
                time.sleep(1)
            elif choice == 'next':
                total_pages = (len(items) + 9) // 10
                page = min(page + 1, total_pages - 1)
            elif choice == 'back':
                page = max(page - 1, 0)
            elif choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(items):
                    bid, binfo = items[idx]
                    if any(b['id'] == bid for b in selected):
                        print(Colors.red + f"[!] Box '{binfo['name']}' đã được chọn!" + Colors.reset)
                    else:
                        selected.append({'id': bid, 'name': binfo['name']})
                        print(Colors.green + f"[+] Đã chọn: {binfo['name']}" + Colors.reset)
                    time.sleep(1)
                else:
                    print(Colors.red + "[!] Số không hợp lệ!" + Colors.reset)
                    time.sleep(1)
            else:
                print(Colors.red + "[!] Lựa chọn không hợp lệ!" + Colors.reset)
                time.sleep(1)

        return selected

    # ── Spam Link ────────────────────────────────────────────────────────────
    def _build_payload(self, url, thumb, group_id):
        ts, fw, src = mk()
        ext  = jd(streamUrl="", stream_icon="", tType=1, artist="", src="zalo.me",
                   thumb_src_type=0, count="", expired_time=0, brand_name="Zalo Video",
                   tHeight=256, type=12, link_sub_type=1, mediaTitle="BO LA TA MINH PHAT SIEU BA DAO HEHE", linkType=12, tWidth=486)
        ref  = jd(type=3, data=jd(id=fw, logSrcType=2, ts=ts, fwLvl=1,
                                   rootMsgRef={"id": src, "ts": ts - 1000}))
        info = jd(link=url, linkTitle=url, linkDesc="", linkThumb=thumb,
                   linkType="", extData=ext, message=self._message_content, reference=ref)
        dlog = jd(fw={"pmsg": {"st": 2, "ts": ts, "id": fw},
                       "rmsg": {"ts": ts - 1000, "id": src}, "fwLvl": 1})
        return {
            'grids': [{"clientId": ts, "grid": str(group_id), "ttl": 0}],
            'ttl': 0, 'msgType': '3', 'totalIds': 1,
            'msgInfo': info, 'decorLog': dlog
        }

    def spam_link(self, api, box_id, box_name, url, thumb, delay, acc_num):
        print(Colors.green + f"[+] Acc{acc_num} bắt đầu spam link vĩnh viễn → {box_name}" + Colors.reset)
        success = 0
        fail = 0
        i = 0
        while True:
            i += 1
            try:
                pp = self._build_payload(url, thumb, box_id)
                r = api._post(
                    'https://tt-files-wpa.chat.zalo.me/api/group/mforward',
                    params={'zpw_ver': '678', 'zpw_type': '30'},
                    data={'params': api._encode(pp)}
                )
                d = r.json()
                if d.get('errorCode') == 0:
                    success += 1
                    print(Colors.green + f"[ Acc{acc_num} ] [Lần {i}] Gửi thành công → {box_name}" + Colors.reset)
                else:
                    fail += 1
                    print(Colors.red + f"[ Acc{acc_num} ] [Lần {i}] Lỗi {d.get('errorCode')} → {box_name}" + Colors.reset)

                actual_delay = delay + random.uniform(-0.3, 0.3)
                time.sleep(max(0.1, actual_delay))

            except Exception as e:
                fail += 1
                print(Colors.red + f"[!] Acc{acc_num} lỗi gửi [{box_name}]: {e}" + Colors.reset)
                time.sleep(3)

    # ── Main Flow ────────────────────────────────────────────────────────────
    def spam_link_function(self):
        self.clear()
        self.banner()

        configs, num_accounts = self.load_or_create_configs()
        if not configs:
            print(Colors.red + "[!] Không thể tạo config!" + Colors.reset)
            input("Nhấn Enter để tiếp tục...")
            return

        if not self.init_accounts(configs):
            input("Nhấn Enter để tiếp tục...")
            return

        # Nhập tên file chứa nội dung tin nhắn
        self.clear()
        self.banner()
        self._message_content = "𝗧𝗮 𝗠𝗶𝗻𝗵 𝗣𝗵𝗮𝘁 𝗙𝗼𝗿𝗲𝘃𝗲𝗿 𝗔𝗻𝗵 𝗘𝗺 𝗛𝗼𝘁 𝗠𝗲𝘀𝘀𝗲𝗻𝗴𝗲𝗿 /-li /-li"
        while True:
            fname = input(Colors.yellow + "Tên file nội dung tin nhắn (vd: noidung.txt): " + Colors.reset).strip()
            if not fname:
                print(Colors.red + "[!] Vui lòng nhập tên file!" + Colors.reset)
                continue
            if os.path.exists(fname):
                try:
                    with open(fname, "r", encoding="utf-8") as f:
                        content = f.read().strip()
                    if content:
                        self._message_content = content
                        print(Colors.green + f"[+] Đọc file thành công!" + Colors.reset)
                        print(Colors.cyan + f"[Nội dung]: {self._message_content[:80]}{'...' if len(self._message_content) > 80 else ''}" + Colors.reset)
                        time.sleep(1)
                        break
                    else:
                        print(Colors.red + "[!] File trống! Nhập lại." + Colors.reset)
                except Exception as e:
                    print(Colors.red + f"[!] Lỗi đọc file: {e}" + Colors.reset)
            else:
                print(Colors.red + f"[!] Không tìm thấy '{fname}' trong thư mục hiện tại!" + Colors.reset)

        # Nhập URL và thumbnail một lần dùng chung
        self.clear()
        self.banner()
        url   = input(Colors.yellow + "URL link cần spam: " + Colors.reset).strip()
        thumb = input(Colors.yellow + "URL thumbnail (Enter để bỏ qua): " + Colors.reset).strip() or ""

        # Từng account chọn box + cấu hình
        all_account_configs = []
        for account in self.accounts:
            selected_boxes = self.select_boxes(account['number'], account['api'])
            if not selected_boxes:
                print(Colors.red + f"[!] Account {account['number']} không chọn box nào!" + Colors.reset)
                continue

            box_configs = []
            for box in selected_boxes:
                self.clear()
                self.banner()
                print(Colors.yellow + f"Account {account['number']}:" + Colors.reset)
                print(Colors.cyan + f"Box: {box['name']}" + Colors.reset)

                while True:
                    try:
                        delay = float(input(Colors.yellow + "Delay (giây, vd: 0.5): " + Colors.reset).strip())
                        if delay < 0:
                            print(Colors.red + "[!] Delay không âm!" + Colors.reset)
                            continue
                        break
                    except ValueError:
                        print(Colors.red + "[!] Nhập số!" + Colors.reset)

                box_configs.append({'box': box, 'delay': delay})

            if box_configs:
                all_account_configs.append({'account': account, 'boxes': box_configs})

        if not all_account_configs:
            print(Colors.red + "[!] Không có cấu hình nào!" + Colors.reset)
            input("Nhấn Enter để tiếp tục...")
            return

        self.clear()
        self.banner()
        print(Colors.green + "[BẮT ĐẦU SPAM LINK]" + Colors.reset)
        print(Colors.cyan + "-" * 50 + Colors.reset)

        threads = []
        for acc_cfg in all_account_configs:
            account = acc_cfg['account']
            for box_cfg in acc_cfg['boxes']:
                t = threading.Thread(
                    target=self.spam_link,
                    args=(
                        account['api'],
                        box_cfg['box']['id'],
                        box_cfg['box']['name'],
                        url,
                        thumb,
                        box_cfg['delay'],
                        account['number']
                    )
                )
                t.daemon = True
                t.start()
                threads.append(t)

        print(Colors.green + f"[+] Đã khởi động {len(threads)} luồng!" + Colors.reset)

        for t in threads:
            t.join()

        print(Colors.green + "\n[*] TẤT CẢ HOÀN THÀNH!" + Colors.reset)
        input("Nhấn Enter để quay lại menu...")

    # ── Run ──────────────────────────────────────────────────────────────────
    def run(self):
        while True:
            self.clear()
            self.banner()
            self.menu()

            choice = input("Chọn chức năng: ").strip()

            if choice == '1':
                self.spam_link_function()
            elif choice == '0':
                print(Colors.green + "Cảm ơn bạn đã sử dụng!" + Colors.reset)
                break
            else:
                print(Colors.red + "[!] Lựa chọn không hợp lệ!" + Colors.reset)
                time.sleep(1)


if __name__ == "__main__":
    bot = SendLinkBot()
    bot.run()