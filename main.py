from playwright.sync_api import sync_playwright
import os, re
from PIL import Image
import time
import asyncio
from telegram import Bot
from telegram.error import TelegramError
from datetime import datetime, timedelta
import threading

TELEGRAM_BOT_TOKEN = "8397765740:AAHp2ZTsWifRo9jUguH2qv9EB9rnnoA0uW8"
TELEGRAM_CHAT_ID = "-1002455512034"
SEND_INTERVAL_SECONDS = 7200 
CAPTION_TEXT = "*🔥 KÈO THƠM HÔM NAY - VÀO NGAY KẺO LỠ ⚽️*\n\n🔗 [CƯỢC NGAY](https://vua99.com/?modal=SIGN_UP)"

URL = "https://keo.win/keo-bong-da"
OUTPUT_DIR = os.path.join(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "/tmp"), "screenshots")
os.makedirs(OUTPUT_DIR, exist_ok=True)

LAST_MESSAGE_ID_FILE = os.path.join(OUTPUT_DIR, "last_message_id.txt") 

FIXED_HEADER_CLIP = {'x':200, 'y': 800, 'width':800, 'height': 68}
TEMP_HEADER_PATH = os.path.join(OUTPUT_DIR, "fixed_header_clip.png")
LOGO_PATH = os.path.join(os.getcwd(), "logo.png")
LOGO_POSITION = (600, 60)
LOGO_SIZE = (80,50)

LEAGUE_HEADER_SELECTOR = ".w-full.bg-\\[\\#e0e6f4\\].text-header-bottom.text-\\[14px\\].leading-\\[22px\\].font-bold.h-\\[34px\\].flex.items-center.px-\\[10px\\]"
MATCH_ROW_SELECTOR = ".bg-row-background"

MATCHES_TO_KEEP = [
    "FIFA World Cup", "UEFA European Championship", "Copa América", "UEFA Champions League", 
    "UEFA Europa League", "Premier League", "La Liga", "Serie A", "Bundesliga", "Ligue 1", 
    "Olympic Football Tournament", "FA Cup", "Copa del Rey", "Coppa Italia", "DFB-Pokal", 
    "UEFA Europa Conference League", "EFL Championship", "Africa Cup of Nations", "CONCACAF Gold Cup", 
    "AFC Asian Cup", "MLS", "Saudi Pro League", "FIFA World Cup Qualifiers", "AFC U23 Asian Cup", 
    "AFC Champions League", "AFF Mitsubishi Electric Cup", "AFF U23 Championship", "SEA Games Football", 
    "V.League 1", "V.League 2", "AFC Cup", "FA Community Shield", "EFL Cup", "UEFA Super Cup", "Seagames"
]

SENT_LEAGUES_CACHE = {} 
CACHE_EXPIRY_SECONDS = 86400
CACHE_LOCK = threading.Lock() 


def sanitize(name):
    return re.sub(r'[\\/*?:"<>|]', "_", name)

def get_league_name_from_element(league_element, idx):
    title_el = league_element.query_selector(LEAGUE_HEADER_SELECTOR)
    name = title_el.inner_text().strip() if title_el else f"league_{idx}"
    name = re.sub(r'\s*(\d{2}/\d{2}|\d{2}/\d{2}\s*-\s*\d{2}/\d{2}|\(\d{2}/\d{2}\s*-\s*\d{2}/\d{2}\))', '', name).strip()
    return name

def is_league_already_sent(sanitized_league_name):
    with CACHE_LOCK:
        if sanitized_league_name in SENT_LEAGUES_CACHE:
            expiry_time = SENT_LEAGUES_CACHE[sanitized_league_name]
            if datetime.now() < expiry_time:
                return True
            else:
                del SENT_LEAGUES_CACHE[sanitized_league_name]
        return False

def mark_league_as_sent(sanitized_league_name):
    with CACHE_LOCK:
        expiry_time = datetime.now() + timedelta(seconds=CACHE_EXPIRY_SECONDS)
        SENT_LEAGUES_CACHE[sanitized_league_name] = expiry_time
        print(f"-> Đã đánh dấu '{sanitized_league_name}' là đã gửi. Hết hạn: {expiry_time.strftime('%H:%M:%S')}")

def capture_fixed_header(page, clip_rect, output_path):
    if clip_rect["width"] <= 0 or clip_rect["height"] <= 0:

        return False
        
    try:
        page.screenshot(path=output_path, clip=clip_rect)
        return True
    except Exception as e:

        return False

def stitch_images(base_path, header_path, logo_path, output_path, logo_size, logo_pos):
    try:
        base_img = Image.open(base_path)
        header_img = Image.open(header_path)
        logo_img = Image.open(logo_path)

        header_img = header_img.resize((base_img.width, header_img.height))

        new_width = base_img.width
        new_height = base_img.height + header_img.height

        stitched_img = Image.new('RGB', (new_width, new_height), color='white')

        stitched_img.paste(header_img, (0, 0))
        stitched_img.paste(base_img, (0, header_img.height))

        logo_img = logo_img.resize(logo_size)
        if logo_img.mode == 'RGBA':
            stitched_img.paste(logo_img, logo_pos, logo_img)
        else:
            stitched_img.paste(logo_img, logo_pos)

        stitched_img.save(output_path)
        return True
    except FileNotFoundError as e:
        return False
    except Exception as e:
        return False

def read_last_message_id():
    if os.path.exists(LAST_MESSAGE_ID_FILE):
        try:
            with open(LAST_MESSAGE_ID_FILE, 'r') as f:
                return int(f.read().strip())
        except Exception:
            return None
    return None

def save_last_message_id(message_id):
    try:
        with open(LAST_MESSAGE_ID_FILE, 'w') as f:
            f.write(str(message_id))
        print(f"-> Đã lưu Message ID")
    except Exception as e:
        print(f"Lỗi khi lưu Message ID")

async def delete_last_message(bot, chat_id):
    message_id = read_last_message_id()
    if message_id:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
            print(f"Đã xóa tin nhắn")
        except TelegramError as e:
            if "message to delete not found" in str(e).lower() or "bad request: message can't be deleted" in str(e).lower():
                 print(f"Tin nhắn cũ ID không tồn tại")
            else:
                print(f"Lỗi khi xóa tin nhắn")
        except Exception as e:
             print(f"Lỗi không xác định")


def capture_and_stitch_core(p):
    browser = None
    temp_filepath = "" 
    target_league_name = None
    
    try:
        browser = p.chromium.launch(headless=True) 
        page = browser.new_page(viewport={"width": 1600, "height": 3000})
        page.goto(URL)
        page.wait_for_load_state("networkidle", timeout=30000) 

        if not capture_fixed_header(page, FIXED_HEADER_CLIP, TEMP_HEADER_PATH):
            return None
        
        page.mouse.wheel(0, 20000)
        page.wait_for_timeout(2000) 
        time.sleep(1) 

        leagues = page.query_selector_all('[class="flex flex-col"]')
        
        target_league = None 
        for idx, league in enumerate(leagues):
            league_name = get_league_name_from_element(league, idx)
            sanitized_name = sanitize(league_name) 
            league.scroll_into_view_if_needed()
            time.sleep(0.3) 
            
            if is_league_already_sent(sanitized_name):
                continue

            if any(m.lower() in league_name.lower() for m in MATCHES_TO_KEEP):
                target_league = league
                target_league_name = sanitized_name + "_Prioritized"
                break 

        if target_league is None:
            for idx, league in enumerate(leagues):
                league_name = get_league_name_from_element(league, idx)
                sanitized_name = sanitize(league_name)
                
                if not is_league_already_sent(sanitized_name):
                    target_league = league
                    target_league_name = sanitized_name + "_FirstOnWeb"
                    break
                else:
                    pass 

        if target_league:
            target_league.scroll_into_view_if_needed()
            page.wait_for_timeout(1000) 

            title_el = target_league.query_selector(LEAGUE_HEADER_SELECTOR)
            match_rows = target_league.query_selector_all(MATCH_ROW_SELECTOR) 
            
            all_boxes = []
            title_box = None

            if title_el:
                title_box = title_el.bounding_box()
                if title_box and title_box["width"] > 0 and title_box["height"] > 0:
                    all_boxes.append(title_box)

            for m in match_rows:
                box = m.bounding_box()
                if box and box["width"] > 0 and box["height"] > 0:
                    all_boxes.append(box)

            if not all_boxes:
                return None
            
            x0 = min(b["x"] for b in all_boxes)
            y0 = min(b["y"] for b in all_boxes)
            x1 = max(b["x"] + b["width"] for b in all_boxes)
            y1 = max(b["y"] + b["height"] for b in all_boxes)

            if len(match_rows) == 0 and title_box:
                y1 += 50

            clip_rect = {
                "x": 200, 
                "y": max(0, y0),
                "width": 800, 
                "height": max(1, y1 - y0)
            }
            
            if clip_rect["width"] > 0 and clip_rect["height"] > 0:
                temp_filepath = os.path.join(OUTPUT_DIR, f"TEMP_{target_league_name}.png")
                
                page.screenshot(path=temp_filepath, clip=clip_rect)
                
                final_filepath = os.path.join(OUTPUT_DIR, f"{target_league_name}_FINAL.png")
                
                if stitch_images(temp_filepath, TEMP_HEADER_PATH, LOGO_PATH, final_filepath, LOGO_SIZE, LOGO_POSITION):
                    mark_league_as_sent(sanitize(get_league_name_from_element(target_league, 0)))
                    return final_filepath
                else:
                    return None
            else:
                return None
        else:
            return None

    except Exception as e:
        return None
    finally:
        if browser:
            browser.close()
            
def capture_and_stitch_wrapper():
    try:
        with sync_playwright() as p:
            return capture_and_stitch_core(p)
    except Exception as e:
        print(f"LỖI TRONG PLAYWRIGHT")
        return None

async def send_to_telegram_periodically():
    
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    
    while True:
        start_time = time.time()
        final_image_path = None
        
        try:
            await delete_last_message(bot, TELEGRAM_CHAT_ID)

            final_image_path = await asyncio.to_thread(capture_and_stitch_wrapper)

            if final_image_path and os.path.exists(final_image_path):
                print(f"Đã hoàn thành")

                with open(final_image_path, 'rb') as photo_file:
                    message = await bot.send_photo(
                        chat_id=TELEGRAM_CHAT_ID, 
                        photo=photo_file,
                        caption=CAPTION_TEXT, 
                        parse_mode='Markdown' 
                    )
                print(f"Đã gửi ảnh thành công qua Telegram.")
                save_last_message_id(message.message_id)
                os.remove(final_image_path)
                print(f"Đã xóa file")
                
            else:
                print("Bỏ qua chu kỳ")

        except TelegramError as e:
            print(f"LỖI TELEGRAM")
        except Exception as e:
            print(f"LỖI KHÔNG XÁC ĐỊNH")

        finally:
            if os.path.exists(TEMP_HEADER_PATH):
                os.remove(TEMP_HEADER_PATH)
            
            temp_files = [f for f in os.listdir(OUTPUT_DIR) if f.startswith("TEMP_") and f.endswith(".png")]
            for temp_f in temp_files:
                try:
                    os.remove(os.path.join(OUTPUT_DIR, temp_f))
                except Exception as e:
                    print(f"Lỗi khi xóa file tạm {temp_f}: {e}")
                    
        end_time = time.time()
        elapsed_time = end_time - start_time
        
        wait_time = max(0, SEND_INTERVAL_SECONDS - elapsed_time)
        print(f"Chu kỳ hoàn thành")
        await asyncio.sleep(wait_time) 


if __name__ == "__main__":
    print("Bắt đầu")
    try:
        asyncio.run(send_to_telegram_periodically())
    except KeyboardInterrupt:
        print("Đã dừng chương trình.")
    except RuntimeError as e:
        if "Event loop is closed" in str(e):
             print("Đã dừng chương trình")
        else:
             print(f"Lỗi Runtime không xác định")
