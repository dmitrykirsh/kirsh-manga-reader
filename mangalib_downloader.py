import os
import re
import time
import requests
import json
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

class MangaLibDownloadThread(QThread):
    progress = pyqtSignal(int, int, str)
    status = pyqtSignal(str)
    finished = pyqtSignal(str, str)
    error = pyqtSignal(str)
    
    def __init__(self, url, dest_root, token="", output_format="Папки с картинками", chapter_range=None):
        super().__init__()
        self.url = url
        self.dest_root = dest_root
        self.token = token
        self.output_format = output_format
        self.chapter_range = chapter_range                               
        self.session = requests.Session()
        
        if 'hentailib' in url:
            self.api_url = "https://hapi.hentaicdn.org/api/manga"
            self.img_url = "img3h.hentaicdn.org"
            self.site_id = "4"
        else:
            self.api_url = "https://api.cdnlibs.org/api/manga"
            self.img_url = "img3.mixlib.me"
            self.site_id = "1"
    
    def pack_to_cbz(self, manga_folder, volume_name, chapters_in_volume):
        """Упаковывает том в CBZ с сохранением структуры глав внутри"""
        import zipfile
        import shutil
        from pathlib import Path
        import re
        
        cbz_path = manga_folder / f"{volume_name}.cbz"
        
        with zipfile.ZipFile(cbz_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for chapter in chapters_in_volume:
                chapter_folder = manga_folder / volume_name / chapter
                if not chapter_folder.exists():
                    continue
                
                                               
                images = []
                for ext in ['*.jpg', '*.jpeg', '*.png', '*.webp']:
                    images.extend(chapter_folder.glob(ext))
                
                                     
                def get_number(path):
                    nums = re.findall(r'\d+', path.stem)
                    return int(nums[0]) if nums else 0
                images.sort(key=get_number)
                
                                                          
                for i, img in enumerate(images, 1):
                    arcname = f"Глава {chapter}/{i:03d}{img.suffix}"
                    zf.write(img, arcname)
                
                                              
                shutil.rmtree(chapter_folder)
            
                                
            shutil.rmtree(manga_folder / volume_name)
        
        return cbz_path
    
    def run(self):
        try:
            self.status.emit("Получение информации...")
            
                           
            slug = self.url.split('/manga/')[1].split('/')[0].split('?')[0]
            slug = re.sub(r'[^a-zA-Z0-9\-_]', '', slug)
            
            headers = {
                "Origin": "https://mangalib.me",
                "Referer": "https://mangalib.me/",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "cross-site",
                "Site-Id": self.site_id,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
            }
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            
                            
            resp = requests.get(f"{self.api_url}/{slug}", headers=headers, timeout=10)
            if resp.status_code != 200:
                self.error.emit(f"Манга не найдена (HTTP {resp.status_code}). Возможно, нужен токен.")
                return
            
            manga_name = resp.json().get('data', {}).get('name', 'Unknown')
            manga_name = re.sub(r'[\\/*?:"<>|]', '_', manga_name)
            manga_name = re.sub(r'[×★✓✔✘®™©]', '_', manga_name)
            
                   
            resp = requests.get(f"{self.api_url}/{slug}/chapters", headers=headers, timeout=10)
            if resp.status_code != 200:
                self.error.emit(f"Не удалось получить главы (HTTP {resp.status_code}). Возможно, нужен токен.")
                return
            
            data = resp.json()
            
                                   
            chapters_list = []
            if isinstance(data, dict):
                if 'data' in data and isinstance(data['data'], list):
                    chapters_list = data['data']
                elif 'chapters' in data and isinstance(data['chapters'], list):
                    chapters_list = data['chapters']
            
            if not chapters_list:
                if not self.token:
                    self.error.emit("Для этой манги нужна авторизация. Введите токен в настройках.")
                else:
                    self.error.emit("Не удалось найти главы")
                return
            
            chapters = []
            for ch in chapters_list:
                if not isinstance(ch, dict):
                    continue
                vol = str(ch.get('volume', '0'))
                num = str(ch.get('number', '0'))
                chapters.append({
                    'vol': vol,
                    'num': num,
                    'name': f"Vol.{vol} Ch.{num}"
                })
            
                                          
            if self.chapter_range and self.output_format != "CBZ (архив)":
                start, end = self.chapter_range
                filtered = []
                for ch in chapters:
                    ch_num = int(ch['num'])
                    if start is not None and ch_num < start:
                        continue
                    if end is not None and ch_num > end:
                        continue
                    filtered.append(ch)
                chapters = filtered
                print(f"Отфильтровано глав: {len(chapters)} из {len(filtered) if 'filtered' in dir() else '?'}")
            
            if not chapters:
                self.error.emit("Главы не найдены")
                return
            
                                       
            volumes = {}
            for ch in chapters:
                vol = ch['vol']
                if vol not in volumes:
                    volumes[vol] = []
                volumes[vol].append(ch['num'])
            
            manga_path = Path(self.dest_root) / manga_name
            total_volumes = len(volumes)
            current_volume = 0
            
                              
            for vol_num, chapters_in_vol in volumes.items():
                current_volume += 1
                self.status.emit(f"Том {vol_num} ({current_volume}/{total_volumes})")
                
                                          
                for idx, ch in enumerate([c for c in chapters if c['vol'] == vol_num], 1):
                    total_in_vol = len(chapters_in_vol)
                    
                    self.progress.emit(idx, total_in_vol, ch['name'])
                    
                    self.status.emit(f"Скачивание: {ch['name']}")
                    
                                       
                    resp = requests.get(f"{self.api_url}/{slug}/chapter",
                                        params={'volume': ch['vol'], 'number': ch['num']},
                                        headers=headers, timeout=10)
                    
                    if resp.status_code != 200:
                        continue
                    
                    pages = resp.json().get('data', {}).get('pages', [])
                    
                    if not pages:
                        continue
                    
                                     
                    folder = manga_path / f"vol{vol_num}" / ch['num']
                    folder.mkdir(parents=True, exist_ok=True)
                    
                                        
                    for j, page in enumerate(pages, 1):
                        page_url = page.get('url', '') if isinstance(page, dict) else str(page)
                        if page_url.startswith('/'):
                            page_url = page_url[1:]
                        img_url = f"https://{self.img_url}/{page_url}"
                        
                        try:
                            img_resp = requests.get(img_url, timeout=30, headers={
                                'Referer': 'https://mangalib.me/',
                                'User-Agent': 'Mozilla/5.0'
                            })
                            if img_resp.status_code == 200:
                                (folder / f"{j:03d}.jpg").write_bytes(img_resp.content)
                            time.sleep(0.2)
                        except Exception:
                            continue
                    
                    time.sleep(0.5)
                
                                                                                
                if self.output_format == "CBZ (архив)":
                    self.status.emit(f"Упаковка тома {vol_num} в CBZ...")
                    self.pack_to_cbz(manga_path, f"vol{vol_num}", chapters_in_vol)
            
           
                                                        
            if self.output_format != "CBZ (архив)":
                self.finished.emit(manga_name, str(manga_path))
            else:
                                                          
                remaining_folders = [f for f in manga_path.iterdir() if f.is_dir()]
                if not remaining_folders:
                    self.finished.emit(manga_name, str(manga_path))
                else:
                    self.finished.emit(manga_name, str(manga_path))
            
        except Exception as e:
            self.error.emit(str(e))