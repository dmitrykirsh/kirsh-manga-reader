import sys
import os

                                                      
os.environ["QT_LOGGING_RULES"] = "*.debug=false;qt.gui.icc=false;qt.gui.imageio=false"

import json
import zipfile
import shutil
import hashlib
import urllib.request
import requests
import re
import ctypes
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('KirshMangaReader.2.0')
except:
    pass
from pathlib import Path
from natsort import natsorted
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QFileDialog, QScrollArea,
    QGridLayout, QLabel, QStackedWidget, QProgressBar,
    QDialog, QMenu, QMessageBox, QComboBox, QTabBar,
    QGraphicsView, QGraphicsScene, QSlider, QInputDialog, QTabWidget, QLineEdit, QListWidget)
from PyQt6.QtGui import QPixmap, QImage, QPainter, QAction, QIcon
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QThread
from mangalib_downloader import MangaLibDownloadThread
from comx_downloader import ComXDownloadThread

def get_driver_path():
    """Возвращает путь к chromedriver.exe"""
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    local_driver = os.path.join(base_path, "chromedriver.exe")
    if os.path.exists(local_driver):
        return local_driver
    return None

                                                                
if getattr(sys, 'frozen', False):
                            
                                                                                  
    DATA_DIR = sys._MEIPASS
                                           
    CONFIG_DIR = os.path.dirname(sys.executable)
else:
                                              
    DATA_DIR = os.path.dirname(os.path.abspath(__file__))
    CONFIG_DIR = DATA_DIR

                                                                              
USER_DATA_DIR = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~\\AppData\\Local')), 'KirshMangaReader')
os.makedirs(USER_DATA_DIR, exist_ok=True)

CONFIG_PATH = os.path.join(USER_DATA_DIR, "reader_config.json")
TOKEN_PATH = os.path.join(USER_DATA_DIR, "mangalib_token.json")
COVERS_DIR = os.path.join(USER_DATA_DIR, "custom_covers")
os.makedirs(COVERS_DIR, exist_ok=True)

                                                                 
OLD_CONFIG_PATH = os.path.join(CONFIG_DIR, "reader_config.json")
if os.path.exists(OLD_CONFIG_PATH) and not os.path.exists(CONFIG_PATH):
    try:
        shutil.move(OLD_CONFIG_PATH, CONFIG_PATH)
    except:
        pass

try:
    import rarfile
                                                                                          
    unrar_path = os.path.join(DATA_DIR, "UnRAR.exe")
    if os.path.exists(unrar_path):
        rarfile.UNRAR_TOOL = unrar_path
        RAR_SUPPORT = True
    else:
        RAR_SUPPORT = False
except ImportError:
    RAR_SUPPORT = False

VALID_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp', '.bmp')
ARCHIVE_EXTENSIONS = ('.zip', '.cbz', '.rar', '.cbr')
COVER_CACHE = {}

def get_custom_cover_path(item_path):
    if not item_path: return None
    h = hashlib.md5(os.path.abspath(item_path).encode('utf-8')).hexdigest()
    return os.path.join(COVERS_DIR, f"{h}.png")

def get_cover_bytes(item_path, is_folder=True):
    cp = get_custom_cover_path(item_path)
    if cp and os.path.exists(cp):
        try:
            with open(cp, 'rb') as f:
                return f.read()
        except: pass
    
    if is_folder:
        return find_first_cover_in_folder(item_path)
    else:
        if item_path in COVER_CACHE:
            return COVER_CACHE[item_path]
        try:
            manga = MangaItem(item_path)
            data = manga.get_page_data(0)
            manga.close_archive()
            return data
        except:
            return None

def find_first_cover_in_folder(folder_path):
    cp = get_custom_cover_path(folder_path)
    if cp and os.path.exists(cp):
        try:
            with open(cp, 'rb') as f: return f.read()
        except: pass
    
    if folder_path in COVER_CACHE:
        return COVER_CACHE[folder_path]
    
    try:
        items = natsorted(os.listdir(folder_path))
    except Exception:
        return None
        
    for item in items:
        path = os.path.join(folder_path, item)
        if os.path.isfile(path) and item.lower().endswith(ARCHIVE_EXTENSIONS):
            f_cp = get_custom_cover_path(path)
            if f_cp and os.path.exists(f_cp):
                try:
                    with open(f_cp, 'rb') as f: return f.read()
                except: pass
            manga = MangaItem(path)
            if manga.pages:
                data = manga.get_page_data(0)
                manga.close_archive()
                if data:
                    COVER_CACHE[folder_path] = data
                    return data
        elif os.path.isdir(path):
            if item.startswith('.'): continue
            try: sub = os.listdir(path)
            except: sub = []
            
            if any(f.lower().endswith(VALID_EXTENSIONS) for f in sub):
                s_cp = get_custom_cover_path(path)
                if s_cp and os.path.exists(s_cp):
                    try:
                        with open(s_cp, 'rb') as f: return f.read()
                    except: pass
                manga = MangaItem(path)
                if manga.pages:
                    data = manga.get_page_data(0)
                    if data:
                        COVER_CACHE[folder_path] = data
                        return data
            else:
                data = find_first_cover_in_folder(path)
                if data:
                    COVER_CACHE[folder_path] = data
                    return data
    return None

class MangaItem:
    GLOBAL_CACHE = {}
    
    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        self.display_name = os.path.splitext(self.name)[0] if path.lower().endswith(ARCHIVE_EXTENSIONS) else self.name
        self.is_archive = path.lower().endswith(ARCHIVE_EXTENSIONS)
        self.pages = []
        self.real_archive_type = None 
        self._archive_handle = None 
        self.load_pages_list()

    def load_pages_list(self):
        if self.path in MangaItem.GLOBAL_CACHE:
            self.pages = MangaItem.GLOBAL_CACHE[self.path]
            if self.path.lower().endswith(('.zip', '.cbz')): self.real_archive_type = 'zip'
            else: self.real_archive_type = 'rar'
            return

        if not self.is_archive:
            try:
                self.pages = [f for f in os.listdir(self.path) if f.lower().endswith(VALID_EXTENSIONS)]
            except Exception: self.pages = []
            self.pages = natsorted(self.pages)
            return

        if self.path.lower().endswith(('.zip', '.cbz')):
            try:
                with zipfile.ZipFile(self.path, 'r') as z:
                    self.pages = [f for f in z.namelist() if f.lower().endswith(VALID_EXTENSIONS)]
                    self.real_archive_type = 'zip'
            except Exception:
                if RAR_SUPPORT:
                    try:
                        with rarfile.RarFile(self.path, 'r') as r:
                            self.pages = [f for f in r.namelist() if f.lower().endswith(VALID_EXTENSIONS)]
                            self.real_archive_type = 'rar'
                    except Exception: pass
        elif RAR_SUPPORT and self.path.lower().endswith(('.rar', '.cbr')):
            try:
                with rarfile.RarFile(self.path, 'r') as r:
                    self.pages = [f for f in r.namelist() if f.lower().endswith(VALID_EXTENSIONS)]
                    self.real_archive_type = 'rar'
            except Exception:
                try:
                    with zipfile.ZipFile(self.path, 'r') as z:
                        self.pages = [f for f in z.namelist() if f.lower().endswith(VALID_EXTENSIONS)]
                        self.real_archive_type = 'zip'
                except Exception: pass
                
        self.pages = natsorted(self.pages)
        if self.pages:
            MangaItem.GLOBAL_CACHE[self.path] = self.pages

    def open_archive(self):
        if not self.is_archive or self._archive_handle: return
        try:
            if self.real_archive_type == 'zip':
                self._archive_handle = zipfile.ZipFile(self.path, 'r')
            elif self.real_archive_type == 'rar' and RAR_SUPPORT:
                self._archive_handle = rarfile.RarFile(self.path, 'r')
        except Exception: self._archive_handle = None

    def close_archive(self):
        if self._archive_handle:
            try: self._archive_handle.close()
            except: pass
            self._archive_handle = None

    def get_page_data(self, index):
        if not self.pages or index < 0 or index >= len(self.pages): return None
        if self.path in COVER_CACHE and index == 0:
            return COVER_CACHE[self.path]
        page_name = self.pages[index]
        try:
            if self.is_archive:
                if not self._archive_handle: self.open_archive()
                if self._archive_handle: 
                    data = self._archive_handle.read(page_name)
                    if index == 0: COVER_CACHE[self.path] = data
                    return data
            else:
                with open(os.path.join(self.path, page_name), 'rb') as f:
                    data = f.read()
                    if index == 0: COVER_CACHE[self.path] = data
                    return data
        except Exception: return None
        return None

class ReaderView(QGraphicsView):
    return_to_library = pyqtSignal()
    progress_changed = pyqtSignal(str, int, int)
    last_page_reached = pyqtSignal(bool)
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.current_manga = None
        self.current_page_idx = 0
        self.pixmap_item = None
        self.is_zoomed = False

    def load_manga(self, manga_item, start_page=0):
        self.current_manga = manga_item
        self.current_manga.open_archive() 
        self.current_page_idx = start_page
        self.is_zoomed = False
        self.show_page()

    def show_page(self):
        if not self.current_manga: return
        data = self.current_manga.get_page_data(self.current_page_idx)
        if data:
            image = QImage()
            image.loadFromData(data)
            pixmap = QPixmap.fromImage(image)
            
            self.scene.clear()
            self.pixmap_item = self.scene.addPixmap(pixmap)
            self.scene.setSceneRect(self.pixmap_item.pixmap().rect().toRectF())
            
            self.fit_to_height()
            self.progress_changed.emit(self.current_manga.path, self.current_page_idx, len(self.current_manga.pages))
            
            is_last = (self.current_page_idx == len(self.current_manga.pages) - 1)
            self.last_page_reached.emit(is_last)

    def fit_to_height(self):
        if self.pixmap_item and self.pixmap_item.pixmap().height() > 0:
            self.fitInView(self.pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
            scale_factor = self.viewport().height() / self.pixmap_item.pixmap().height()
            self.resetTransform()
            self.scale(scale_factor, scale_factor)
            self.centerOn(self.pixmap_item)

    def toggle_zoom(self, pos):
        if not self.pixmap_item: return
        self.is_zoomed = not self.is_zoomed
        if self.is_zoomed:
            self.resetTransform()
            self.scale(1.8, 1.8)
            self.centerOn(pos)
        else:
            self.fit_to_height()

    def next_page(self):
        if self.current_manga and self.current_page_idx < len(self.current_manga.pages) - 1:
            self.current_page_idx += 1
            self.is_zoomed = False
            self.show_page()

    def prev_page(self):
        if self.current_manga and self.current_page_idx > 0:
            self.current_page_idx -= 1
            self.is_zoomed = False
            self.show_page()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.1 if event.angleDelta().y() > 0 else 0.9
            self.scale(factor, factor)
            self.is_zoomed = True
            event.accept()
            return
        
        if not self.is_zoomed:
            if event.angleDelta().y() > 0: self.prev_page()
            else: self.next_page()
        else: super().wheelEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Right: self.next_page()
        elif event.key() == Qt.Key.Key_Left: self.prev_page()
        elif event.key() == Qt.Key.Key_Escape: self.return_to_library.emit()
        else: super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.XButton1:
            self.return_to_library.emit()
            event.accept()
            return
        elif event.button() == Qt.MouseButton.RightButton:
            self.fit_to_height()
            self.is_zoomed = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        scene_pos = self.mapToScene(event.pos())
        self.toggle_zoom(scene_pos)

    def resizeEvent(self, event):
        if not self.is_zoomed: self.fit_to_height()
        super().resizeEvent(event)

class ReaderPage(QWidget):
    back_clicked = pyqtSignal()
    next_chapter_requested = pyqtSignal()
    
    def __init__(self, reader_view):
        super().__init__()
        self.reader_view = reader_view
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        self.top_panel = QWidget()
        self.top_panel.setObjectName("TopPanel")
        panel_layout = QHBoxLayout(self.top_panel)
        panel_layout.setContentsMargins(15, 5, 15, 5)
        
        self.btn_back = QPushButton("← В библиотеку")
        self.btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_back.clicked.connect(self.back_clicked.emit)
        
        self.title_label = QLabel("")
        self.title_label.setObjectName("ReaderTitle")
        
        panel_layout.addWidget(self.btn_back)
        
                           
        self.btn_toc = QPushButton("📑 Оглавление")
        self.btn_toc.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toc.clicked.connect(self.show_toc)
        panel_layout.addWidget(self.btn_toc)
        
        panel_layout.addWidget(self.title_label)
        panel_layout.addStretch()
        
        main_layout.addWidget(self.top_panel)
        
        self.viewer_container = QWidget()
        container_layout = QGridLayout(self.viewer_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addWidget(self.reader_view, 0, 0)
        
        self.hint_frame = QWidget()
        self.hint_frame.setObjectName("HintFrame")
        self.hint_frame.setStyleSheet("""
            QWidget#HintFrame {
                background-color: rgba(25, 25, 25, 0.95);
                border: 2px solid #ff9800;
                border-radius: 8px;
            }
            QLabel { color: white; font-size: 12px; }
        """)
        hint_layout = QVBoxLayout(self.hint_frame)
        hint_layout.setContentsMargins(12, 12, 12, 12)
        hint_layout.setSpacing(8)
        
        hint_header = QHBoxLayout()
        lbl_hint_title = QLabel("<b>Навигация ридера:</b>")
        lbl_hint_title.setStyleSheet("color: #ff9800; font-size: 13px; font-weight: bold;")
        btn_close_x = QPushButton("×")
        btn_close_x.setFixedSize(18, 18)
        btn_close_x.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close_x.setStyleSheet("background: transparent; border: none; color: white; font-size: 16px; font-weight: bold; padding: 0;")
        btn_close_x.clicked.connect(self.hint_frame.hide)
        
        hint_header.addWidget(lbl_hint_title)
        hint_header.addStretch()
        hint_header.addWidget(btn_close_x)
        hint_layout.addLayout(hint_header)
        
        lbl_hint = QLabel(
            "• Стрелки влево/вправо или Колесико — Листать страницы<br>"
            "• <b>Ctrl + Колесико</b> — Изменение масштаба страницы<br>"
            "• <b>ПКМ (Правый клик)</b> — Мгновенный сброс масштаба<br>"
            "• Двойной клик ЛКМ — Приблизить в точку<br>"
            "• <b>F11</b> — Полноэкранный режим<br>"
            "• Esc — Вернуться в главное меню"
        )
        btn_close_hint = QPushButton("Понятно, больше не показывать")
        btn_close_hint.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close_hint.setStyleSheet("background-color: #ff9800; color: black; font-weight: bold; border: none; padding: 6px; border-radius: 4px;")
        btn_close_hint.clicked.connect(self.close_hint_permanently)
        
        hint_layout.addWidget(lbl_hint)
        hint_layout.addWidget(btn_close_hint)
        container_layout.addWidget(self.hint_frame, 0, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        self.hint_frame.hide()

        self.next_chap_widget = QWidget()
        nc_layout = QHBoxLayout(self.next_chap_widget)
        nc_layout.setContentsMargins(0, 0, 25, 25)
        self.btn_next_chap = QPushButton("Следующая глава →")
        self.btn_next_chap.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_next_chap.setStyleSheet("""
            QPushButton { 
                background-color: #28a745; color: white; padding: 12px 24px; 
                font-weight: bold; font-size: 14px; border-radius: 6px; border: none; 
            }
            QPushButton:hover { background-color: #218838; }
        """)
        self.btn_next_chap.clicked.connect(self.next_chapter_requested.emit)
        nc_layout.addStretch()
        nc_layout.addWidget(self.btn_next_chap)
        
        container_layout.addWidget(self.next_chap_widget, 0, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        self.next_chap_widget.hide()
        
        main_layout.addWidget(self.viewer_container)

        self.bottom_panel = QWidget()
        self.bottom_panel.setObjectName("BottomPanel")
        bottom_layout = QHBoxLayout(self.bottom_panel)
        bottom_layout.setContentsMargins(20, 5, 20, 5)

        self.btn_page_jump = QPushButton("1 из 1")
        self.btn_page_jump.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_page_jump.clicked.connect(self.show_jump_dialog)

        self.page_slider = QSlider(Qt.Orientation.Horizontal)
        self.page_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.page_slider.sliderMoved.connect(self.handle_slider_move)

        bottom_layout.addWidget(self.btn_page_jump)
        bottom_layout.addWidget(self.page_slider)
        main_layout.addWidget(self.bottom_panel)

        self.reader_view.last_page_reached.connect(self.toggle_next_chapter_button)

    def close_hint_permanently(self):
        self.hint_frame.hide()
        self.reader_view.main_window.config["show_navigation_hint"] = False
        self.reader_view.main_window.save_config()

    def handle_slider_move(self, value):
        self.reader_view.current_page_idx = value - 1
        self.reader_view.show_page()

    def show_jump_dialog(self):
        if not self.reader_view.current_manga: return
        total = len(self.reader_view.current_manga.pages)
        if total <= 0: return
        current = self.reader_view.current_page_idx + 1
        val, ok = QInputDialog.getInt(self, "Перейти к странице", f"Введите страницу (1-{total}):", current, 1, total)
        if ok:
            self.reader_view.current_page_idx = val - 1
            self.reader_view.show_page()

    def set_title(self, text):
        self.title_label.setText(text)

    def toggle_next_chapter_button(self, visible):
        if visible and self.has_next_chapter():
            self.next_chap_widget.show()
        else:
            self.next_chap_widget.hide() 
            
    def show_toc(self):
        """Показывает диалог с оглавлением"""
        if not self.reader_view.current_manga:
            QMessageBox.information(self, "Оглавление", "Ничего не открыто")
            return
        
        manga = self.reader_view.current_manga
        
                 
        self.debug_archive(manga)
        
        chapters = self.get_chapter_list(manga)
        
                         
        print(f"Найдено глав/страниц: {len(chapters)}")
        print(f"Первые 10: {chapters[:10]}")
        
        if not chapters:
            QMessageBox.information(self, "Оглавление", "Нет доступных глав")
            return
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Оглавление")
        dialog.setMinimumSize(400, 500)
        dialog.setModal(True)
        
        layout = QVBoxLayout(dialog)
        
                     
        layout.addWidget(QLabel("Выберите главу:"))
        self.toc_list = QListWidget()
        for ch in chapters:
            self.toc_list.addItem(ch)
        layout.addWidget(self.toc_list)
        
                         
        btn_go = QPushButton("📖 Перейти к главе")
        btn_go.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_go.clicked.connect(lambda: self.go_to_chapter(dialog, manga))
        layout.addWidget(btn_go)
        
                       
        btn_cancel = QPushButton("Отмена")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(dialog.reject)
        layout.addWidget(btn_cancel)
        
                               
        self.toc_list.itemDoubleClicked.connect(lambda: self.go_to_chapter(dialog, manga))
        
        dialog.exec()
    
    def get_chapter_list(self, manga):
        """Возвращает список глав - папки, которые содержат картинки напрямую"""
        import zipfile
        from pathlib import Path
        import re
        
        chapters = []
        
        if manga.is_archive:
            try:
                if manga.real_archive_type == 'zip':
                    with zipfile.ZipFile(manga.path, 'r') as zf:
                        all_names = zf.namelist()
                        
                        candidate_folders = set()
                        for name in all_names:
                            if '/' in name and name.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                                folder_path = '/'.join(name.split('/')[:-1])
                                last_folder = folder_path.split('/')[-1]
                                candidate_folders.add(last_folder)
                        
                        if candidate_folders:
                                                                                     
                            if len(candidate_folders) == 1:
                                folder = list(candidate_folders)[0]
                                prefix = f"{folder}/"
                                images = [Path(name).stem for name in all_names 
                                         if name.startswith(prefix) and name.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]
                                chapters = sorted(images)
                            else:
                                def extract_num(name):
                                    nums = re.findall(r'\d+', name)
                                    return int(nums[0]) if nums else 0
                                chapters = sorted(candidate_folders, key=extract_num)
                        else:
                            images = [Path(name).stem for name in all_names 
                                     if name.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]
                            chapters = sorted(images)
                
                elif manga.real_archive_type == 'rar' and RAR_SUPPORT:
                    import rarfile
                    with rarfile.RarFile(manga.path, 'r') as rf:
                        all_names = rf.namelist()
                        
                        candidate_folders = set()
                        for name in all_names:
                            if '/' in name and name.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                                folder_path = '/'.join(name.split('/')[:-1])
                                last_folder = folder_path.split('/')[-1]
                                candidate_folders.add(last_folder)
                        
                        if candidate_folders:
                                                                          
                            if len(candidate_folders) == 1:
                                folder = list(candidate_folders)[0]
                                prefix = f"{folder}/"
                                images = [Path(name).stem for name in all_names 
                                         if name.startswith(prefix) and name.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]
                                chapters = sorted(images)
                            else:
                                def extract_num(name):
                                    nums = re.findall(r'\d+', name)
                                    return int(nums[0]) if nums else 0
                                chapters = sorted(candidate_folders, key=extract_num)
                        else:
                            images = [Path(name).stem for name in all_names 
                                     if name.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]
                            chapters = sorted(images)
                        
            except Exception as e:
                print(f"Ошибка чтения архива: {e}")
        else:
                       
            try:
                manga_path = Path(manga.path)
                subdirs = [d for d in manga_path.iterdir() if d.is_dir()]
                if subdirs:
                                                                             
                    if len(subdirs) == 1:
                        folder = subdirs[0]
                        images = [f.stem for f in folder.iterdir() 
                                 if f.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp')]
                        chapters = sorted(images)
                    else:
                        chapters = [d.name for d in sorted(subdirs)]
                else:
                    images = [f.stem for f in manga_path.iterdir() 
                             if f.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp')]
                    chapters = sorted(images)
            except Exception as e:
                print(f"Ошибка чтения папки: {e}")
        
        return chapters
    
    def get_first_page_of_chapter(self, manga, chapter_name):
        """Возвращает индекс первой страницы главы или страницы"""
        import zipfile
        from pathlib import Path
        
        if manga.is_archive:
            try:
                if manga.real_archive_type == 'zip':
                    archive = zipfile.ZipFile(manga.path, 'r')
                elif manga.real_archive_type == 'rar' and RAR_SUPPORT:
                    import rarfile
                    archive = rarfile.RarFile(manga.path, 'r')
                else:
                    return -1
                
                with archive as ar:
                    all_files = [name for name in ar.namelist() 
                                if name.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]
                    all_files.sort()
                    
                                                                   
                    for idx, page in enumerate(all_files):
                        page_stem = Path(page).stem
                        if page_stem == chapter_name:
                            return idx
                    
                                                    
                    for idx, page in enumerate(all_files):
                        if '/' in page:
                            parts = page.split('/')
                            last_folder = parts[-2] if len(parts) >= 2 else None
                            if last_folder == chapter_name:
                                return idx
                            
            except Exception as e:
                print(f"Ошибка: {e}")
        else:
                       
            try:
                manga_path = Path(manga.path)
                all_images = []
                for root, dirs, files in os.walk(manga_path):
                    for f in files:
                        if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                            all_images.append(os.path.join(root, f))
                all_images.sort()
                
                for idx, img in enumerate(all_images):
                    if Path(img).stem == chapter_name:
                        return idx
            except Exception as e:
                print(f"Ошибка: {e}")
        
        return -1

    def go_to_chapter(self, dialog, manga):
        """Переходит к выбранной главе"""
        current_item = self.toc_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Оглавление", "Выберите главу из списка")
            return
        
        chapter_name = current_item.text()
        
        page_num = self.get_first_page_of_chapter(manga, chapter_name)
        
        if page_num >= 0:
            self.reader_view.current_page_idx = page_num
            self.reader_view.show_page()
            dialog.accept()
        else:
            QMessageBox.warning(self, "Ошибка", f"Не удалось найти главу: {chapter_name}")
        
        return -1

    def has_next_chapter(self):
        if not self.reader_view.current_manga: return False
        current_path = self.reader_view.current_manga.path
        parent_dir = os.path.dirname(current_path)
        try:
            siblings = natsorted([os.path.join(parent_dir, f) for f in os.listdir(parent_dir)
                                  if (os.path.isfile(os.path.join(parent_dir, f)) and f.lower().endswith(ARCHIVE_EXTENSIONS))
                                  or (os.path.isdir(os.path.join(parent_dir, f)) and not f.startswith('.'))])
            idx = siblings.index(current_path)
            return idx < len(siblings) - 1
        except Exception: return False
        
    def _extract_number(self, name):
        """Извлекает число из названия главы для сортировки"""
        import re
        nums = re.findall(r'\d+', name)
        return int(nums[0]) if nums else 0
        
    def debug_archive(self, manga):
        """Отладка: выводит структуру архива"""
        import zipfile
        import rarfile
        
        print("\n=== ОТЛАДКА АРХИВА ===")
        print(f"Путь: {manga.path}")
        print(f"Тип: {'ZIP' if manga.real_archive_type == 'zip' else 'RAR' if manga.real_archive_type == 'rar' else 'Неизвестный'}")
        
        if manga.real_archive_type == 'zip':
            with zipfile.ZipFile(manga.path, 'r') as zf:
                files = zf.namelist()
                print(f"Всего файлов в архиве: {len(files)}")
                print("\nПервые 20 элементов:")
                for i, name in enumerate(files[:20]):
                    print(f"  {i+1}. {name}")
                print("\nТолько папки (уникальные):")
                folders = set()
                for name in files:
                    if '/' in name:
                        parts = name.split('/')
                        for i in range(len(parts) - 1):
                            folder = '/'.join(parts[:i+1])
                            folders.add(folder)
                for f in sorted(folders)[:20]:
                    print(f"  {f}")
        print("=======================\n")

class LibraryCard(QWidget):
    clicked = pyqtSignal(object)
    menu_action_triggered = pyqtSignal(str, str)
    
    def __init__(self, manga_item, current_page=0, card_width=220):
        super().__init__()
        self.manga_item = manga_item
        self.current_page = current_page
        self.cover_data = get_cover_bytes(self.manga_item.path, is_folder=False)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.cover_label = QLabel()
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setStyleSheet("background-color: #2a2a2a; border-radius: 8px;")

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        
        total_pages = len(self.manga_item.pages)
        self.progress_bar.setMaximum(total_pages if total_pages > 0 else 100)
        self.progress_bar.setValue(current_page + 1 if current_page > 0 or total_pages == 1 else current_page)
        if current_page == 0 and total_pages > 0: self.progress_bar.setValue(0)

        self.title_label = QLabel(self.manga_item.display_name)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #ffffff;")
        self.title_label.setToolTip(self.manga_item.display_name)

        layout.addWidget(self.cover_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.title_label)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
         
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        
        self.update_size(card_width)

    def update_size(self, card_width):
        self.setFixedWidth(card_width)
        w_cover = card_width - 20
        h_cover = int(w_cover * 1.4)
        self.cover_label.setFixedSize(w_cover, h_cover)
        
        if self.cover_data:
            img = QImage()
            img.loadFromData(self.cover_data)
            pix = QPixmap.fromImage(img).scaled(w_cover, h_cover, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            self.cover_label.setPixmap(pix)
        else:
            self.cover_label.setText("📖")
            self.cover_label.setStyleSheet("background-color: #2a2a2a; border-radius: 8px; font-size: 32px;")
            
        self.progress_bar.setFixedSize(w_cover, 6)
        
        self.title_label.setFixedWidth(w_cover)
        self.title_label.setFixedHeight(20)
        self.title_label.setWordWrap(False)
        font_metrics = self.title_label.fontMetrics()
        elided_text = font_metrics.elidedText(self.manga_item.display_name, Qt.TextElideMode.ElideRight, w_cover)
        self.title_label.setText(elided_text)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton: self.clicked.emit(self.manga_item)

    def show_context_menu(self, pos):
        menu = QMenu(self)
        
        act_reset = QAction("🔄 Удалить прогресс", self)
        act_read = QAction("✅ Отметить как прочитанное", self)
        act_cover = QAction("🖼 Изменить обложку", self)
        act_rem_cover = QAction("🗑 Удалить свою обложку", self)
        act_open_folder = QAction("📂 Открыть в проводнике", self)
        act_del = QAction("❌ Удалить с устройства", self)
        
        act_reset.triggered.connect(lambda: self.menu_action_triggered.emit("reset", self.manga_item.path))
        act_read.triggered.connect(lambda: self.menu_action_triggered.emit("mark_read", self.manga_item.path))
        act_cover.triggered.connect(lambda: self.menu_action_triggered.emit("change_cover", self.manga_item.path))
        act_rem_cover.triggered.connect(lambda: self.menu_action_triggered.emit("remove_cover", self.manga_item.path))
        act_open_folder.triggered.connect(lambda: self.menu_action_triggered.emit("open_folder", self.manga_item.path))
        act_del.triggered.connect(lambda: self.menu_action_triggered.emit("delete", self.manga_item.path))
        
        menu.addAction(act_reset)
        menu.addAction(act_read)
        menu.addSeparator()
        menu.addAction(act_cover)
        menu.addAction(act_rem_cover)
        menu.addSeparator()
        menu.addAction(act_open_folder)
        menu.addSeparator()
        menu.addAction(act_del)
        menu.exec(self.mapToGlobal(pos))

class LibraryFolderCard(QWidget):
    clicked = pyqtSignal(str)
    menu_action_triggered = pyqtSignal(str, str)
    
    def __init__(self, folder_path, display_name, progress_val, progress_max, card_width=220):
        super().__init__()
        self.folder_path = folder_path
        self.display_name = display_name
        self.progress_val = progress_val
        self.progress_max = progress_max
        self.cover_data = get_cover_bytes(folder_path, is_folder=True)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.cover_label = QLabel()
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setStyleSheet("background-color: #2d261d; border-radius: 8px;")

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMaximum(progress_max if progress_max > 0 else 100)
        self.progress_bar.setValue(progress_val)

        self.title_label = QLabel(display_name)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #ff9800;")
        self.title_label.setToolTip(display_name)

        layout.addWidget(self.cover_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.title_label)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
         
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        
        self.update_size(card_width)

    def update_size(self, card_width):
        self.setFixedWidth(card_width)
        w_cover = card_width - 20
        h_cover = int(w_cover * 1.4)
        self.cover_label.setFixedSize(w_cover, h_cover)
        
        if self.cover_data:
            img = QImage()
            img.loadFromData(self.cover_data)
            pix = QPixmap.fromImage(img).scaled(w_cover, h_cover, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            self.cover_label.setPixmap(pix)
            self.cover_label.setText("") 
        else:
            self.cover_label.setText("📁")
            self.cover_label.setStyleSheet("background-color: #2d261d; border-radius: 8px; font-size: 48px;")

        self.progress_bar.setFixedSize(w_cover, 6)
        
        self.title_label.setFixedWidth(w_cover)
        self.title_label.setFixedHeight(20)
        self.title_label.setWordWrap(False)
        font_metrics = self.title_label.fontMetrics()
        elided_text = font_metrics.elidedText(self.display_name, Qt.TextElideMode.ElideRight, w_cover)
        self.title_label.setText(elided_text)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton: self.clicked.emit(self.folder_path)

    def show_context_menu(self, pos):
        menu = QMenu(self)
        
        act_reset = QAction("🔄 Удалить прогресс папки", self)
        act_read = QAction("✅ Отметить как прочитанное", self)
        act_cover = QAction("🖼 Изменить обложку", self)
        act_rem_cover = QAction("🗑 Удалить свою обложку", self)
        act_open_folder = QAction("📂 Открыть в проводнике", self)
        act_del = QAction("❌ Удалить папку с устройства", self)
        
        act_reset.triggered.connect(lambda: self.menu_action_triggered.emit("reset", self.folder_path))
        act_read.triggered.connect(lambda: self.menu_action_triggered.emit("mark_read", self.folder_path))
        act_cover.triggered.connect(lambda: self.menu_action_triggered.emit("change_cover", self.folder_path))
        act_rem_cover.triggered.connect(lambda: self.menu_action_triggered.emit("remove_cover", self.folder_path))
        act_open_folder.triggered.connect(lambda: self.menu_action_triggered.emit("open_folder", self.folder_path))
        act_del.triggered.connect(lambda: self.menu_action_triggered.emit("delete", self.folder_path))
        
        menu.addAction(act_reset)
        menu.addAction(act_read)
        menu.addSeparator()
        menu.addAction(act_cover)
        menu.addAction(act_rem_cover)
        menu.addSeparator()
        menu.addAction(act_open_folder)
        menu.addSeparator()
        menu.addAction(act_del)
        menu.exec(self.mapToGlobal(pos))

class SettingsDialog(QDialog):
    def __init__(self, parent, current_root, current_theme, current_accent):
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.setFixedSize(480, 420)
        self.rescan_requested = False
        
        main_layout = QVBoxLayout(self)
        self.tab_widget = QTabWidget()
        
        tab_general = QWidget()
        gen_layout = QVBoxLayout(tab_general)
        
        lbl_app_title = QLabel("Kirsh Manga Reader")
        lbl_app_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #ff9800;")
        lbl_app_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        lbl_app_version = QLabel("Версия: 2.0")
        lbl_app_version.setStyleSheet("font-size: 12px; color: #888888; margin-bottom: 10px;")
        lbl_app_version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        gen_layout.addWidget(lbl_app_title)
        gen_layout.addWidget(lbl_app_version)
        gen_layout.addSpacing(5)

        gen_layout.addWidget(QLabel("Корневая папка Manga:"))
        self.lbl_path = QLabel(current_root if current_root else "Не выбрана")
        self.lbl_path.setWordWrap(True)
        self.lbl_path.setStyleSheet("font-weight: bold;")
        gen_layout.addWidget(self.lbl_path)
        
        btn_browse = QPushButton("Обзор...")
        btn_browse.clicked.connect(self.browse)
        gen_layout.addWidget(btn_browse)
        gen_layout.addSpacing(10)
        
        gen_layout.addWidget(QLabel("Цветовая тема устройства:"))
        self.combo_theme = QComboBox()
        self.combo_theme.addItems(["Тёмная", "Глубокая чёрная", "Тёмно-синяя", "Тёмно-красная", "Тёмно-зелёная", "Тёмно-фиолетовая", "Тёмно-серая"])
        self.combo_theme.setCurrentText(current_theme)
        gen_layout.addWidget(self.combo_theme)
        gen_layout.addSpacing(10)

        gen_layout.addWidget(QLabel("Акцентный цвет интерфейса:"))
        self.combo_accent = QComboBox()
        self.combo_accent.addItems(["Розовый", "Оранжевый", "Синий", "Зелёный", "Красный", "Фиолетовый"])
        self.combo_accent.setCurrentText(current_accent)
        gen_layout.addWidget(self.combo_accent)
        
        tab_help = QWidget()
        help_layout = QVBoxLayout(tab_help)
        
        help_text = QLabel(
            "<b>Kirsh Manga Reader v2.0</b><br><br>"
            "<b>📖 Чтение манги:</b><br>"
            "• Стрелки влево/вправо или Колесико — Листать страницы<br>"
            "• <b>Ctrl + Колесико</b> — Изменение масштаба страницы<br>"
            "• <b>ПКМ (Правый клик)</b> — Сброс масштаба по высоте окна<br>"
            "• Двойной клик ЛКМ — Приблизить в точку<br>"
            "• <b>F11</b> — Полноэкранный режим<br>"
            "• <b>Esc</b> — Вернуться в библиотеку<br><br>"
            "<b>📥 Скачивание манги (новое в v2.0):</b><br>"
            "• Кнопка <b>📥</b> на верхней панели — открыть диалог скачивания<br>"
            "• Поддерживаются сайты: <b>MangaLib/b> и <b>Com-X.life</b><br>"
            "• Для Com-X.life и 18+ контента MangaLib нужна авторизация (кнопка в диалоге)<br>"
            "• Авторизация выполняется <b>1 раз через браузер</b>, данные сохраняются<br>"
            "• Прогресс скачивания отображается в отдельном окне<br>"
            "• После скачивания манга <b>автоматически добавляется в библиотеку</b><br><br>"
            "<b>⚙ Управление библиотекой:</b><br>"
            "• <b>Ползунок справа</b> — изменение размера обложек<br>"
            "• <b>Правый клик по карточке</b> — контекстное меню:<br>"
            " • Удалить прогресс / Отметить как прочитанное<br>"
            " • Изменить / удалить обложку<br>"
            " • <b>Открыть в проводнике</b> — выделить файл/папку<br>"
            " • Удалить с устройства<br>"
            "• Вкладки: <b>Библиотека</b> / <b>Продолжить чтение</b> / <b>Завершено</b><br><br>"
            "<b>🔑 Авторизация:</b><br>"
            "• <b>MangaLib (18+):</b> в диалоге скачивания нажмите «Получить токен»<br>"
            "• <b>Com-X.life:</b> в диалоге скачивания нажмите «Авторизоваться»<br>"
            "• Браузер откроется автоматически, после входа данные сохранятся"
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet("font-size: 12px; line-height: 1.4;")
        
        scroll_help = QScrollArea()
        scroll_help.setWidgetResizable(True)
        scroll_help_content = QWidget()
        sh_layout = QVBoxLayout(scroll_help_content)
        sh_layout.addWidget(help_text)
        scroll_help.setWidget(scroll_help_content)
        help_layout.addWidget(scroll_help)
        
        self.tab_widget.addTab(tab_general, "Основные")
        self.tab_widget.addTab(tab_help, "Справка")
        main_layout.addWidget(self.tab_widget)
        
                              
        ACCENTS_MAP = {
            "Розовый": "#ff69b4", "Оранжевый": "#ff9800", "Синий": "#0078D7",
            "Зелёный": "#28a745", "Красный": "#dc3545", "Фиолетовый": "#9c27b0"
        }
        accent_hex = ACCENTS_MAP.get(current_accent, "#ff9800")

        btn_rescan = QPushButton("🔄 Пересканировать")
        btn_rescan.setStyleSheet(f"background-color: {accent_hex}; color: white; padding: 8px; font-weight: bold; border-radius: 4px;")
        btn_rescan.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_rescan.clicked.connect(self.trigger_rescan)
        main_layout.addWidget(btn_rescan)

        btn_save = QPushButton("Сохранить изменения")
        btn_save.setStyleSheet("background-color: #28a745; color: white; padding: 8px; font-weight: bold; border-radius: 4px;")
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.clicked.connect(self.accept)
        main_layout.addWidget(btn_save)
        
    def browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите корневую папку Manga", self.lbl_path.text())
        if folder: 
            self.lbl_path.setText(folder)
    
    def trigger_rescan(self):
        self.rescan_requested = True
        self.accept()
        
class DownloadDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Скачать мангу")
        self.setFixedSize(550, 400)
        self.selected_loader = None
        self.url = None
        
        layout = QVBoxLayout(self)
        
                     
        layout.addWidget(QLabel("Сайт:"))
        self.site_combo = QComboBox()
        self.site_combo.addItems(["MangaLib", "Com-X.life"])
        self.site_combo.currentTextChanged.connect(self.on_site_changed)
        layout.addWidget(self.site_combo)
        
                            
        self.auth_status_label = QLabel("")
        self.auth_status_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self.auth_status_label)
        
                            
        self.auth_button = QPushButton("🔑 Авторизация")
        self.auth_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.auth_button.clicked.connect(self.do_auth)
        self.auth_button.hide()
        layout.addWidget(self.auth_button)
        
                      
        layout.addWidget(QLabel("Ссылка на мангу:"))
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://mangalib.me/ru/manga/... или https://com-x.life/...")
        layout.addWidget(self.url_input)
        
                           
        layout.addWidget(QLabel("Формат сохранения:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["Папки с картинками", "CBZ (архив)"])
        self.format_combo.setCurrentIndex(1)
        layout.addWidget(self.format_combo)
        
        layout.addStretch()
        
                
        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("Скачать")
        btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Отмена")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)
        
        self.on_site_changed(self.site_combo.currentText())
    
    def on_site_changed(self, site):
        if "Com-X" in site:
            self.check_comx_auth_status()
        elif "MangaLib" in site:
            self.check_mangalib_auth_status()
    
    def check_comx_auth_status(self):
        from pathlib import Path
        import os
        
        cookies_file = Path(os.environ.get('LOCALAPPDATA', '')) / 'KirshMangaReader' / 'comx_cookies.json'
        if cookies_file.exists():
            self.auth_status_label.setText("✅ Авторизован (куки есть)")
            self.auth_status_label.setStyleSheet("color: #28a745; font-size: 11px;")
            self.auth_button.setText("🔄 Обновить авторизацию")
        else:
            self.auth_status_label.setText("❌ Не авторизован (нужно авторизоваться для большинства манг)")
            self.auth_status_label.setStyleSheet("color: #dc3545; font-size: 11px;")
            self.auth_button.setText("🔑 Авторизоваться")
        self.auth_button.show()
    
    def check_mangalib_auth_status(self):
        from pathlib import Path
        import os
        import json
        
        token_path = Path(os.environ.get('LOCALAPPDATA', '')) / 'KirshMangaReader' / 'mangalib_token.json'
        
                 
        print(f"DEBUG: token_path = {token_path}")
        print(f"DEBUG: exists = {token_path.exists()}")
        
        token = None
        if token_path.exists():
            try:
                with open(token_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    token = data.get("token", "")
                print(f"DEBUG: token = {token[:20] if token else 'None'}...")
            except Exception as e:
                print(f"DEBUG: ошибка чтения: {e}")
        
        if token:
            self.auth_status_label.setText("✅ Токен есть (можно скачивать 18+)")
            self.auth_status_label.setStyleSheet("color: #28a745; font-size: 11px;")
            self.auth_button.setText("🔄 Обновить токен")
        else:
            self.auth_status_label.setText("❌ Нет токена (для 18+ нужна авторизация)")
            self.auth_status_label.setStyleSheet("color: #ff9800; font-size: 11px;")
            self.auth_button.setText("🔑 Получить токен")
        self.auth_button.show()
    
    def do_auth(self):
        site = self.site_combo.currentText()
        if "Com-X" in site:
            self.auth_button.setEnabled(False)
            self.auth_button.setText("⏳ Открываю браузер...")
            
            temp_loader = ComXDownloadThread("https://com-x.life", "")
            temp_loader.auth_via_browser()
            
            self.auth_button.setEnabled(True)
            self.check_comx_auth_status()
            
        elif "MangaLib" in site:
            QMessageBox.information(self, "Авторизация MangaLib", 
                "Откроется браузер.\n\nВойдите в аккаунт на mangalib.me\n\nПосле входа токен будет сохранён автоматически.")
            
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager
            import time
            import json
            from pathlib import Path
            import os
            
            chrome_options = Options()
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.get("https://mangalib.me")
            
            token = None
            for i in range(120):
                time.sleep(1)
                try:
                    token = driver.execute_script("""
                        try {
                            var auth = localStorage.getItem('auth');
                            if (auth) {
                                var data = JSON.parse(auth);
                                return data.token.access_token;
                            }
                        } catch(e) {}
                        return null;
                    """)
                    if token:
                        break
                except:
                    pass
            
            driver.quit()
            
            if token:
                token_path = Path(os.environ.get('LOCALAPPDATA', '')) / 'KirshMangaReader' / 'mangalib_token.json'
                token_path.parent.mkdir(parents=True, exist_ok=True)
                with open(token_path, 'w', encoding='utf-8') as f:
                    json.dump({"token": token}, f)
                QMessageBox.information(self, "Успех", "Токен сохранён!")
            else:
                QMessageBox.warning(self, "Ошибка", "Не удалось получить токен")
            
            self.check_mangalib_auth_status()
    
    def get_data(self):
        site = self.site_combo.currentText()
        url = self.url_input.text().strip()
        output_format = self.format_combo.currentText()
        return site, url, output_format

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Kirsh Manga Reader v2.0")
        
                                     
        icon_path = os.path.join(DATA_DIR, "icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
                                      
        
        self.resize(1350, 850)
        self.config = {
            "root_dir": "", "progress": {}, "theme": "Тёмная", "accent": "Розовый", 
            "archive_cache": {}, "card_width": 220, "show_navigation_hint": True
        }
        self.load_config()
        
        MangaItem.GLOBAL_CACHE = self.config.get("archive_cache", {})
        self.current_dir = self.config["root_dir"]

        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)

        self.main_library_page = QWidget()
        main_lib_layout = QVBoxLayout(self.main_library_page)
        main_lib_layout.setContentsMargins(15, 15, 15, 15)

        top_bar = QHBoxLayout()
        self.btn_lib_back = QPushButton("← На уровень вверх")
        self.btn_lib_back.setStyleSheet("padding: 8px 16px; font-weight: bold; border-radius: 4px;")
        self.btn_lib_back.clicked.connect(self.navigate_up)
        self.btn_lib_back.hide()
        top_bar.addWidget(self.btn_lib_back)
        
                                                           
        top_bar.addStretch()
        
                          
        top_bar.addWidget(QLabel("Размер:"))
        self.card_width_slider = QSlider(Qt.Orientation.Horizontal)
        self.card_width_slider.setRange(150, 350)
        self.card_width_slider.setValue(self.config.get("card_width", 220))
        self.card_width_slider.setFixedWidth(150)
        self.card_width_slider.valueChanged.connect(self.on_card_width_changed)
        top_bar.addWidget(self.card_width_slider)
        
                                                       
        top_bar.addSpacing(15)
        
                                    
        self.btn_download = QPushButton("📥")
        self.btn_download.setFixedSize(36, 36)
        self.btn_download.setStyleSheet("font-size: 18px; border-radius: 4px;")
        self.btn_download.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_download.setToolTip("Скачать мангу по ссылке (MangaLib, Com-X.life)")
        self.btn_download.clicked.connect(self.show_download_dialog)
        top_bar.addWidget(self.btn_download)
        
                                          
        top_bar.addSpacing(8)
        
                                  
        self.btn_settings = QPushButton("⚙")
        self.btn_settings.setFixedSize(36, 36)
        self.btn_settings.setStyleSheet("font-size: 18px; border-radius: 4px;")
        self.btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_settings.setToolTip("Настройки программы")
        self.btn_settings.clicked.connect(self.open_settings)
        top_bar.addWidget(self.btn_settings)
        
                                     
        top_bar.addSpacing(10)
        
        main_lib_layout.addLayout(top_bar)

        tab_bar_container = QWidget()
        tab_bar_layout = QHBoxLayout(tab_bar_container)
        tab_bar_layout.setContentsMargins(0, 0, 0, 10)
        
        self.custom_tab_bar = QTabBar()
        self.custom_tab_bar.addTab("Библиотека")
        self.custom_tab_bar.addTab("Продолжить чтение")
        self.custom_tab_bar.addTab("Завершено")
        self.custom_tab_bar.currentChanged.connect(self.handle_tab_changed)
        
        tab_bar_layout.addStretch()
        tab_bar_layout.addWidget(self.custom_tab_bar)
        tab_bar_layout.addStretch()
        main_lib_layout.addWidget(tab_bar_container)

        self.tab_stack = QStackedWidget()
        
        self.scroll_all = QScrollArea()
        self.grid_all = QGridLayout()
        self.init_tab_scroll(self.scroll_all, self.grid_all)
        
        self.scroll_reading = QScrollArea()
        self.grid_reading = QGridLayout()
        self.init_tab_scroll(self.scroll_reading, self.grid_reading)
        
        self.scroll_done = QScrollArea()
        self.grid_done = QGridLayout()
        self.init_tab_scroll(self.scroll_done, self.grid_done)

        self.tab_stack.addWidget(self.scroll_all)
        self.tab_stack.addWidget(self.scroll_reading)
        self.tab_stack.addWidget(self.scroll_done)
        
                                                                                         
        main_lib_layout.addWidget(self.tab_stack, 1)

        self.empty_btn = QPushButton("Библиотека пуста.\nНажмите сюда, чтобы указать папку с мангой в настройках.")
        self.empty_btn.setObjectName("EmptyLibraryButton")
        self.empty_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.empty_btn.clicked.connect(self.open_settings)
        main_lib_layout.addWidget(self.empty_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        self.empty_btn.hide()

        self.reader_view = ReaderView(self)
        self.reader_page = ReaderPage(self.reader_view)
        
        self.reader_view.return_to_library.connect(self.show_library)
        self.reader_page.back_clicked.connect(self.show_library)
        self.reader_page.next_chapter_requested.connect(self.open_next_chapter)
        self.reader_view.progress_changed.connect(self.update_reader_ui_progress)

        self.stacked_widget.addWidget(self.main_library_page)
        self.stacked_widget.addWidget(self.reader_page)

        self.apply_theme()

        if self.current_dir and os.path.exists(self.current_dir):
            QTimer.singleShot(50, lambda: self.scan_library(self.current_dir))
        else:
            QTimer.singleShot(50, lambda: self.scan_library(""))
    
    def handle_comx_auth(self):
        """Обработка авторизации для Com-X (вызывается в главном потоке)"""
                                                                      
        if not hasattr(self, 'loader') or not isinstance(self.loader, ComXDownloadThread):
            return
        
        reply = QMessageBox.question(self, "Авторизация Com-X", 
                                     "Откроется браузер.\n\nВойдите в аккаунт на com-x.life\n\nПосле входа нажмите OK.",
                                     QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        
        if reply == QMessageBox.StandardButton.Ok:
                                                                               
            import threading
            threading.Thread(target=self.loader.auth_via_browser, daemon=True).start()
        else:
            self.loader.error.emit("Авторизация отменена пользователем")
            self.loader.terminate()
            if hasattr(self, 'progress_dialog') and self.progress_dialog:
                self.progress_dialog.close()

    def init_tab_scroll(self, scroll_area, grid_layout):
        scroll_area.setWidgetResizable(True)
        container = QWidget()
        grid_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        grid_layout.setSpacing(20)
        container.setLayout(grid_layout)
        scroll_area.setWidget(container)

    def load_config(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    for k, v in loaded.items():
                        self.config[k] = v
            except Exception: pass

    def save_config(self):
        self.config["archive_cache"] = MangaItem.GLOBAL_CACHE
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=4)

    def on_card_width_changed(self, value):
        self.config["card_width"] = value
        for grid in [self.grid_all, self.grid_reading, self.grid_done]:
            for i in range(grid.count()):
                widget = grid.itemAt(i).widget()
                if widget and hasattr(widget, 'update_size'):
                    widget.update_size(value)
        self.save_config()
        self.refresh_grid_layout()

    def update_reader_ui_progress(self, path, page_idx, total_pages):
        self.config["progress"][path] = {"page": page_idx, "total": total_pages}
        self.save_config()
        
        self.reader_page.btn_page_jump.setText(f"{page_idx + 1} из {total_pages}")
        self.reader_page.page_slider.blockSignals(True)
        self.reader_page.page_slider.setRange(1, total_pages)
        self.reader_page.page_slider.setValue(page_idx + 1)
        self.reader_page.page_slider.blockSignals(False)

    def open_settings(self):
        dlg = SettingsDialog(self, self.config["root_dir"], self.config["theme"], self.config["accent"])
        if dlg.exec() == QDialog.DialogCode.Accepted:
            if dlg.rescan_requested: 
                COVER_CACHE.clear()
                MangaItem.GLOBAL_CACHE = {}
            self.config["root_dir"] = dlg.lbl_path.text()
            self.config["theme"] = dlg.combo_theme.currentText()
            self.config["accent"] = dlg.combo_accent.currentText()
            self.current_dir = dlg.lbl_path.text()
            self.save_config()
            self.apply_theme()
            self.scan_library(self.current_dir) 

    def apply_theme(self):
        theme = self.config.get("theme", "Тёмная")
        accent_name = self.config.get("accent", "Розовый")
        
        THEMES = {
            "Тёмная": "#1e1e1e", "Глубокая чёрная": "#000000", "Тёмно-синяя": "#111a2e",
            "Тёмно-красная": "#2b1111", "Тёмно-зелёная": "#112415", "Тёмно-фиолетовая": "#1f112e",
            "Тёмно-серая": "#2d3238"
        }
        PANELS = {
            "Тёмная": "#2a2a2a", "Глубокая чёрная": "#111111", "Тёмно-синяя": "#1b263b",
            "Тёмно-красная": "#3d1818", "Тёмно-зелёная": "#1b331e", "Тёмно-фиолетовая": "#2e1b40",
            "Тёмно-серая": "#3a3f47"
        }
        ACCENTS = {
            "Розовый": "#ff69b4", "Оранжевый": "#ff9800", "Синий": "#0078D7",
            "Зелёный": "#28a745", "Красный": "#dc3545", "Фиолетовый": "#9c27b0"
        }
        
        bg = THEMES.get(theme, "#1e1e1e")
        panel = PANELS.get(theme, "#2a2a2a")
        accent = ACCENTS.get(accent_name, "#ff69b4")
        text = "#ffffff"

        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ background-color: {bg}; color: {text}; }}
            QScrollArea, QScrollArea QWidget {{ background-color: {bg}; border: none; }}
            QPushButton {{ background-color: {panel}; color: {text}; border: 1px solid #444; padding: 6px; border-radius: 4px; }}
            QPushButton:hover {{ background-color: {accent}; color: white; }}  
            QDialog {{ background-color: {bg}; }}
            QComboBox, QCheckBox {{ background-color: {panel}; color: {text}; padding: 4px; border: 1px solid #444; }}
            
            QProgressBar {{ background-color: #333; border: none; border-radius: 3px; }}
            QProgressBar::chunk {{ background-color: {accent}; border-radius: 3px; }}
            
        QSlider::groove:horizontal {{ 
            border: 1px solid #444; 
            height: 8px; 
            background: {panel}; 
            border-radius: 4px; 
        }}
        QSlider::sub-page:horizontal {{ 
            background: {accent}; 
            border-radius: 4px; 
        }}
        QSlider::add-page:horizontal {{ 
            background: transparent; 
        }}
        QSlider::handle:horizontal {{ 
            background: {text}; 
            border: 1px solid #444; 
            width: 16px; 
            margin-top: -4px; 
            margin-bottom: -4px; 
            border-radius: 8px; 
        }}
        QSlider::handle:horizontal:hover {{
            background: {accent};
        }}
            
            /* === НОВЫЕ СТИЛИ ДЛЯ СКРОЛЛБАРА === */
            QScrollBar:vertical {{
                border: none;
                background: {panel};
                width: 12px;
                border-radius: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {accent};
                min-height: 30px;
                border-radius: 6px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {text};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
                height: 0px;
            }}

            QScrollBar:horizontal {{
                border: none;
                background: {panel};
                height: 12px;
                border-radius: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:horizontal {{
                background: {accent};
                min-width: 30px;
                border-radius: 6px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {text};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: none;
                width: 0px;
            }}
            /* ================================== */

            QTabBar {{ background: transparent; }}
            QTabBar::tab {{ 
                background: {panel}; 
                color: {text}; 
                padding: 8px 24px; 
                font-weight: bold; 
                border: 2px solid {accent}; 
                border-radius: 12px; 
                margin: 0 4px; 
            }}
            QTabBar::tab:hover {{ background: {accent}; color: white; }}
            QTabBar::tab:selected {{ background: {accent}; color: white; border: 2px solid {accent}; }}
            
            QTabWidget::pane {{ border: 1px solid #444; background: {bg}; border-radius: 8px; margin-top: -1px; }}
            
            QPushButton#EmptyLibraryButton {{
                background-color: {panel};
                border: 2px dashed {accent};
                padding: 30px;
                font-size: 15px;
                font-weight: bold;
                border-radius: 12px;
                min-width: 400px;
            }}
            QPushButton#EmptyLibraryButton:hover {{
                background-color: {accent};
                color: white;
                border-style: solid;
            }}
            
            QMenu {{ background-color: {panel}; color: {text}; border: 1px solid #444; padding: 5px; border-radius: 6px; }}
            QMenu::item {{ padding: 6px 28px 6px 16px; border-radius: 4px; background-color: transparent; }}
            QMenu::item:selected {{ background-color: {accent}; color: white; }}
            QMenu::separator {{ height: 1px; background-color: #444; margin: 4px 6px; }}
        """)
        self.reader_view.setStyleSheet(f"background-color: {bg}; border: none;")
        self.reader_page.top_panel.setStyleSheet(f"background-color: {panel}; max-height: 50px;")
        self.reader_page.bottom_panel.setStyleSheet(f"background-color: {panel}; max-height: 50px;")
        self.reader_page.title_label.setStyleSheet(f"color: {text}; font-weight: bold; font-size: 14px; margin-left: 15px;")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.stacked_widget.currentWidget() == self.main_library_page:
            self.refresh_grid_layout()

    def refresh_grid_layout(self):
        idx = self.custom_tab_bar.currentIndex()
        if idx == 0: self.rearrange_grid(self.grid_all)
        elif idx == 1: self.rearrange_grid(self.grid_reading)
        elif idx == 2: self.rearrange_grid(self.grid_done)

    def rearrange_grid(self, grid):
        if grid.count() == 0: return
        max_cols = self.get_max_columns()
        widgets = []
        for i in range(grid.count()):
            w = grid.itemAt(i).widget()
            if w: widgets.append(w)
        
        for w in widgets: grid.removeWidget(w)
        
        row, col = 0, 0
        for w in widgets:
            grid.addWidget(w, row, col)
            col += 1
            if col >= max_cols: col = 0; row += 1

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F11:
            if self.isFullScreen(): self.showNormal()
            else: self.showFullScreen()
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.XButton1:
            if self.stacked_widget.currentWidget() == self.main_library_page:
                self.navigate_up()
                event.accept()
                return
        super().mousePressEvent(event)

    def navigate_up(self):
        if self.current_dir and self.current_dir != self.config["root_dir"]:
            self.scan_library(os.path.dirname(self.current_dir))

    def handle_tab_changed(self, index):
        self.tab_stack.setCurrentIndex(index)
        if index == 0: self.scan_library(self.current_dir)
        elif index == 1: self.build_flat_tab("reading")
        elif index == 2: self.build_flat_tab("done")

    def calculate_folder_progress(self, folder_path):
        total_pages_in_folder = 0
        total_pages_read = 0
        try:
            for root, dirs, files in os.walk(folder_path):
                has_images = any(f.lower().endswith(VALID_EXTENSIONS) for f in files)
                has_archives = any(f.lower().endswith(ARCHIVE_EXTENSIONS) for f in files)
                valid_dirs = [d for d in dirs if not d.startswith('.')]
                
                if has_images and not has_archives and not valid_dirs:
                    manga = MangaItem(root)
                    pages_count = len(manga.pages)
                    total_pages_in_folder += pages_count
                    
                    prog_data = self.config["progress"].get(root, None)
                    if isinstance(prog_data, dict):
                        total_pages_read += min(prog_data.get("page", 0) + 1, pages_count)
                else:
                    for f in files:
                        if f.lower().endswith(ARCHIVE_EXTENSIONS):
                            p = os.path.join(root, f)
                            manga = MangaItem(p)
                            pages_count = len(manga.pages)
                            total_pages_in_folder += pages_count
                            
                            prog_data = self.config["progress"].get(p, None)
                            if isinstance(prog_data, dict):
                                total_pages_read += min(prog_data.get("page", 0) + 1, pages_count)
        except Exception: pass
        return total_pages_read, total_pages_in_folder

    def clear_grid(self, grid):
        for i in reversed(range(grid.count())): 
            w = grid.itemAt(i).widget()
            if w: w.deleteLater()

    def show_empty_state(self, grid, message="Тут пока пусто"):
        self.clear_grid(grid)
        label = QLabel(message)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: #888; font-size: 16px; font-weight: bold;")
        grid.addWidget(label, 0, 0)

    def get_max_columns(self):
        width = self.width()
        card_w = self.config.get("card_width", 220) + 20
        cols = (width - 60) // card_w
        return max(1, cols)

    def scan_library(self, target_dir):
        if self.custom_tab_bar.currentIndex() != 0: return
        self.current_dir = target_dir
        self.btn_lib_back.setVisible(self.current_dir != self.config["root_dir"])
        self.clear_grid(self.grid_all)

        if not target_dir or not os.path.exists(target_dir):
            self.tab_stack.hide()
            self.empty_btn.show()
            return

        try: raw_items = os.listdir(target_dir)
        except Exception: raw_items = []

        row, col = 0, 0
        max_cols = self.get_max_columns()
        c_width = self.config.get("card_width", 220)
        has_items = False

        for item in natsorted(raw_items):
            item_path = os.path.join(target_dir, item)
            if os.path.isfile(item_path) and item.lower().endswith(ARCHIVE_EXTENSIONS):
                manga = MangaItem(item_path)
                if manga.pages:
                    card = self.create_manga_card(manga)
                    self.grid_all.addWidget(card, row, col)
                    col += 1
                    has_items = True
            elif os.path.isdir(item_path):
                if item.startswith('.'): continue
                try: sub_files = os.listdir(item_path)
                except: sub_files = []
                
                has_images = any(f.lower().endswith(VALID_EXTENSIONS) for f in sub_files)
                has_archives = any(f.lower().endswith(ARCHIVE_EXTENSIONS) for f in sub_files)
                has_subdirs = any(os.path.isdir(os.path.join(item_path, d)) for d in sub_files)

                if has_images and not has_archives and not has_subdirs:
                    manga = MangaItem(item_path)
                    if manga.pages:
                        card = self.create_manga_card(manga)
                        self.grid_all.addWidget(card, row, col)
                        col += 1
                        has_items = True
                else:
                    f_read, f_total = self.calculate_folder_progress(item_path)
                    f_card = LibraryFolderCard(item_path, item, f_read, f_total, card_width=c_width)
                    f_card.clicked.connect(self.scan_library)
                    f_card.menu_action_triggered.connect(self.handle_menu_action)
                    self.grid_all.addWidget(f_card, row, col)
                    col += 1
                    has_items = True

            if col >= max_cols: col = 0; row += 1

        if not has_items:
            if target_dir == self.config["root_dir"]:
                self.tab_stack.hide()
                self.empty_btn.show()
            else:
                self.tab_stack.show()
                self.empty_btn.hide()
                self.show_empty_state(self.grid_all, "В этой папке пока пусто")
        else:
            self.empty_btn.hide()
            self.tab_stack.show()

    def create_manga_card(self, manga, custom_handler=None):
        prog = self.config["progress"].get(manga.path, {})
        last_page = prog.get("page", 0) if isinstance(prog, dict) else 0
        card = LibraryCard(manga, current_page=last_page, card_width=self.config.get("card_width", 220))
        if custom_handler:
            card.clicked.connect(custom_handler)
        else:
            card.clicked.connect(self.open_manga)
        card.menu_action_triggered.connect(self.handle_menu_action)
        return card

    def build_flat_tab(self, mode):
        grid = self.grid_reading if mode == "reading" else self.grid_done
        self.clear_grid(grid)
        self.btn_lib_back.hide()

        row, col = 0, 0
        max_cols = self.get_max_columns()
        root = self.config["root_dir"]
        c_width = self.config.get("card_width", 220)
        has_items = False
        
        if not root or not os.path.exists(root): 
            self.show_empty_state(grid, "Тут пока пусто")
            return

        if mode == "reading":
            reading_top_items = set()
            for path, data in self.config["progress"].items():
                if not os.path.exists(path): continue
                if isinstance(data, dict):
                    if 0 < data.get("page", 0) < (data.get("total", 0) - 1):
                        rel = os.path.relpath(path, root)
                        top_item_name = rel.split(os.sep)[0]
                        reading_top_items.add(os.path.join(root, top_item_name))

            for item_path in natsorted(list(reading_top_items)):
                if os.path.isfile(item_path) and item_path.lower().endswith(ARCHIVE_EXTENSIONS):
                    manga = MangaItem(item_path)
                    if manga.pages:
                        card = self.create_manga_card(manga)
                        grid.addWidget(card, row, col)
                        col += 1
                        has_items = True
                elif os.path.isdir(item_path):
                    f_read, f_total = self.calculate_folder_progress(item_path)
                    f_card = LibraryFolderCard(item_path, os.path.basename(item_path), f_read, f_total, card_width=c_width)
                    f_card.clicked.connect(self.open_folder_manga_continue)
                    f_card.menu_action_triggered.connect(self.handle_menu_action)
                    grid.addWidget(f_card, row, col)
                    col += 1
                    has_items = True
                if col >= max_cols: col = 0; row += 1
        else:
            completed_top_items = set()
            try: raw_top_items = os.listdir(root)
            except Exception: pass

            for item in raw_top_items:
                if item.startswith('.'): continue
                item_path = os.path.join(root, item)
                
                if os.path.isfile(item_path) and item_path.lower().endswith(ARCHIVE_EXTENSIONS):
                    prog_data = self.config["progress"].get(item_path, None)
                    if isinstance(prog_data, dict):
                        if prog_data.get("page", 0) >= (prog_data.get("total", 0) - 1) and prog_data.get("total", 0) > 0:
                            completed_top_items.add(item_path)
                elif os.path.isdir(item_path):
                    f_read, f_total = self.calculate_folder_progress(item_path)
                    if f_total > 0 and f_read >= (f_total - 5): 
                        completed_top_items.add(item_path)

            for item_path in natsorted(list(completed_top_items)):
                if os.path.isfile(item_path):
                    manga = MangaItem(item_path)
                    if manga.pages:
                        card = self.create_manga_card(manga, custom_handler=self.open_manga_at_end)
                        grid.addWidget(card, row, col)
                        col += 1
                        has_items = True
                else:
                    f_read, f_total = self.calculate_folder_progress(item_path)
                    f_card = LibraryFolderCard(item_path, os.path.basename(item_path), f_read, f_total, card_width=c_width)
                    f_card.clicked.connect(self.open_folder_manga_completed)
                    f_card.menu_action_triggered.connect(self.handle_menu_action)
                    grid.addWidget(f_card, row, col)
                    col += 1
                    has_items = True
                if col >= max_cols: col = 0; row += 1

        if not has_items:
            self.show_empty_state(grid, "Тут пока пусто")

    def open_folder_manga_continue(self, folder_path):
        norm_folder = os.path.abspath(folder_path) + os.sep
        target_path = None
        
        for p, data in self.config["progress"].items():
            if os.path.abspath(p).startswith(norm_folder):
                if isinstance(data, dict):
                    if 0 < data.get("page", 0) < (data.get("total", 0) - 1):
                        target_path = p
                        break
        
        if not target_path:
            try:
                for root, _, files in os.walk(folder_path):
                    manga_files = [os.path.join(root, f) for f in files if f.lower().endswith(ARCHIVE_EXTENSIONS)]
                    if manga_files:
                        target_path = natsorted(manga_files)[0]
                        break
            except: pass

        if target_path:
            manga = MangaItem(target_path)
            if manga.pages:
                self.open_manga(manga) 

    def open_folder_manga_completed(self, folder_path):
        all_files = []
        try:
            for root, _, files in os.walk(folder_path):
                for f in files:
                    if f.lower().endswith(ARCHIVE_EXTENSIONS):
                        all_files.append(os.path.join(root, f))
        except: pass

        if all_files:
            last_file = natsorted(all_files)[-1]
            manga = MangaItem(last_file)
            if manga.pages:
                self.open_manga_at_end(manga)

    def open_manga_at_end(self, manga_item):
        total_pages = len(manga_item.pages)
        last_page = max(0, total_pages - 1)
        self.reader_page.set_title(manga_item.display_name)
        self.reader_view.load_manga(manga_item, last_page)
        self.stacked_widget.setCurrentWidget(self.reader_page)
        self.reader_page.hint_frame.setVisible(self.config.get("show_navigation_hint", True))

    def handle_menu_action(self, action_type, item_path):
        if action_type == "reset":
            self.reset_item_progress(item_path)
            self.scan_library(self.current_dir)
        elif action_type == "mark_read":
            self.mark_item_as_read(item_path)
            self.scan_library(self.current_dir)
        elif action_type == "change_cover":
            self.change_item_cover(item_path)
            self.scan_library(self.current_dir)
        elif action_type == "remove_cover":
            self.remove_item_cover(item_path)
            self.scan_library(self.current_dir)
        elif action_type == "open_folder":                        
            self.open_in_explorer(item_path)
        elif action_type == "delete":
            self.delete_item_from_device(item_path)
            self.scan_library(self.current_dir)

    def change_item_cover(self, item_path):
        msg = QMessageBox(self)
        msg.setWindowTitle("Изменить обложку")
        msg.setText("Выберите способ установки кастомной обложки:")
        btn_file = msg.addButton("Из файла на ПК", QMessageBox.ButtonRole.ActionRole)
        btn_url = msg.addButton("По ссылке из сети", QMessageBox.ButtonRole.ActionRole)
        msg.addButton("Отмена", QMessageBox.ButtonRole.RejectRole)
        msg.exec()
        
        target_cp = get_custom_cover_path(item_path)
        
        if msg.clickedButton() == btn_file:
            file_path, _ = QFileDialog.getOpenFileName(self, "Выберите изображение", "", "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
            if file_path:
                try:
                    shutil.copy(file_path, target_cp)
                    if item_path in COVER_CACHE: COVER_CACHE.pop(item_path)
                except Exception as e: QMessageBox.critical(self, "Ошибка", f"Не удалось скопировать файл: {e}")
                
        elif msg.clickedButton() == btn_url:
            url, ok = QInputDialog.getText(self, "Обложка по ссылке", "Вставьте URL-ссылку на картинку:")
            if ok and url.strip():
                try:
                    req = urllib.request.Request(url.strip(), headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=10) as response:
                        data = response.read()
                    with open(target_cp, 'wb') as f:
                        f.write(data)
                    if item_path in COVER_CACHE: COVER_CACHE.pop(item_path)
                except Exception as e: QMessageBox.critical(self, "Ошибка", f"Не удалось скачать: {e}")

    def remove_item_cover(self, item_path):
        target_cp = get_custom_cover_path(item_path)
        if os.path.exists(target_cp):
            try:
                os.remove(target_cp)
                if item_path in COVER_CACHE: COVER_CACHE.pop(item_path)
                QMessageBox.information(self, "Успех", "Кастомная обложка успешно удалена.")
            except Exception as e: QMessageBox.critical(self, "Ошибка", f"Не удалось удалить файл обложки: {e}")
        else:
            QMessageBox.information(self, "Инфо", "У этого элемента нет кастомной обложки.")

    def reset_item_progress(self, path):
        if os.path.isdir(path):
            norm = os.path.abspath(path) + os.sep
            to_remove = [p for p in self.config["progress"] if os.path.abspath(p).startswith(norm)]
            for p in to_remove: self.config["progress"].pop(p, None)
        else:
            self.config["progress"].pop(path, None)
        self.save_config()

    def mark_item_as_read(self, path):
        if os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                has_images = any(f.lower().endswith(VALID_EXTENSIONS) for f in files)
                has_archives = any(f.lower().endswith(ARCHIVE_EXTENSIONS) for f in files)
                valid_dirs = [d for d in dirs if not d.startswith('.')]
                
                if has_images and not has_archives and not valid_dirs:
                    manga = MangaItem(root)
                    if manga.pages: 
                        self.config["progress"][root] = {"page": len(manga.pages)-1, "total": len(manga.pages)}
                else:
                    for f in files:
                        if f.lower().endswith(ARCHIVE_EXTENSIONS):
                            p = os.path.join(root, f)
                            m = MangaItem(p)
                            if m.pages: 
                                self.config["progress"][p] = {"page": len(m.pages)-1, "total": len(m.pages)}
        else:
            m = MangaItem(path)
            if m.pages: 
                self.config["progress"][path] = {"page": len(m.pages)-1, "total": len(m.pages)}
        self.save_config()

    def delete_item_from_device(self, path):
        reply = QMessageBox.question(self, 'Удаление', f"Удалить файл/папку с устройства?\n{path}",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.reset_item_progress(path)
                if os.path.isdir(path): shutil.rmtree(path)
                else: os.remove(path)
                if path in COVER_CACHE: COVER_CACHE.pop(path)
                if path in MangaItem.GLOBAL_CACHE: MangaItem.GLOBAL_CACHE.pop(path)
                target_cp = get_custom_cover_path(path)
                if os.path.exists(target_cp): os.remove(target_cp)
            except Exception as e: QMessageBox.critical(self, "Ошибка", str(e))
            
    def open_in_explorer(self, path):
        """Открывает папку в проводнике и выделяет файл/папку"""
        import os
        import subprocess
        
        path = os.path.abspath(path)
        
        if not os.path.exists(path):
            QMessageBox.warning(self, "Ошибка", f"Путь не существует:\n{path}")
            return
        
                                                    
        if os.path.isdir(path):
            os.startfile(path)
        else:
                                           
            folder = os.path.dirname(path)
            if os.path.exists(folder):
                subprocess.Popen(f'explorer /select, "{path}"')

    def open_manga(self, manga_item):
        prog = self.config["progress"].get(manga_item.path, {})
        last_page = prog.get("page", 0) if isinstance(prog, dict) else 0
        self.reader_page.set_title(manga_item.display_name)
        self.reader_view.load_manga(manga_item, last_page)
        self.stacked_widget.setCurrentWidget(self.reader_page)
        self.reader_page.hint_frame.setVisible(self.config.get("show_navigation_hint", True))

    def open_next_chapter(self):
        if not self.reader_view.current_manga: return
        current_path = self.reader_view.current_manga.path
        parent_dir = os.path.dirname(current_path)
        try:
            siblings = natsorted([os.path.join(parent_dir, f) for f in os.listdir(parent_dir)
                                  if (os.path.isfile(os.path.join(parent_dir, f)) and f.lower().endswith(ARCHIVE_EXTENSIONS))
                                  or (os.path.isdir(os.path.join(parent_dir, f)) and not f.startswith('.'))])
            idx = siblings.index(current_path)
            if idx < len(siblings) - 1:
                next_path = siblings[idx + 1]
                self.reader_view.current_manga.close_archive()
                
                next_manga = MangaItem(next_path) 
                if next_manga.pages:
                    self.open_manga(next_manga)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка перехода", str(e))

    def show_library(self):
        if self.reader_view.current_manga: self.reader_view.current_manga.close_archive()
        self.stacked_widget.setCurrentWidget(self.main_library_page)
        self.handle_tab_changed(self.custom_tab_bar.currentIndex())
    def show_download_dialog(self):
        dialog = DownloadDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            site, url, output_format = dialog.get_data()
            if not url:
                QMessageBox.warning(self, "Ошибка", "Введите ссылку")
                return
            
            if not self.config.get("root_dir") or not os.path.exists(self.config["root_dir"]):
                QMessageBox.warning(self, "Ошибка", "Сначала укажите корневую папку для манги в настройках")
                return
            
            self.start_download(site, url, output_format)
    
    def start_download(self, site, url, output_format):
        root_dir = self.config["root_dir"]
        
        if "MangaLib" in site:
            token_path = Path(os.environ.get('LOCALAPPDATA', '')) / 'KirshMangaReader' / 'mangalib_token.json'
            token = ""
            if token_path.exists():
                try:
                    with open(token_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        token = data.get("token", "")
                except:
                    pass
            self.loader = MangaLibDownloadThread(url, root_dir, token=token, output_format=output_format)
        else:
            self.loader = ComXDownloadThread(url, root_dir, output_format=output_format)
            self.loader.need_auth.connect(self.handle_comx_auth)
        
              
                        
        self.progress_dialog = QDialog(self)
        self.progress_dialog.setWindowTitle("Скачивание")
        self.progress_dialog.setFixedSize(450, 180)
        layout = QVBoxLayout(self.progress_dialog)
        
        self.progress_label = QLabel("Подготовка...")
        layout.addWidget(self.progress_label)
        
                                            
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)
        
        self.progress_chapter = QLabel("")
        layout.addWidget(self.progress_chapter)
        
                        
        warning_label = QLabel("⚠️ Не закрывайте это окно до завершения загрузки")
        warning_label.setStyleSheet("color: #ff9800; font-size: 11px; margin-top: 8px;")
        warning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(warning_label)
        
        btn_cancel = QPushButton("Отмена")
        btn_cancel.clicked.connect(self.cancel_download)
        layout.addWidget(btn_cancel)
        
                            
        self.loader.progress.connect(self.update_download_progress)
        self.loader.status.connect(self.update_download_status)
        self.loader.finished.connect(self.download_finished)
        self.loader.error.connect(self.download_error)
        
        self.progress_dialog.show()
        self.loader.start()
    
    def update_download_progress(self, current, total, chapter_name):
        percent = int(current / total * 100) if total > 0 else 0
        self.progress_bar.setValue(percent)
        self.progress_chapter.setText(f"Глава {current} из {total}: {chapter_name}")
    
    def update_download_status(self, status):
        self.progress_label.setText(status)
    
    def cancel_download(self):
        if hasattr(self, 'loader') and self.loader.isRunning():
            self.loader.terminate()
            self.loader.wait()
        self.progress_dialog.close()
    
    def download_finished(self, manga_title, folder_path):
        self.progress_dialog.close()
        QMessageBox.information(self, "Готово", f"Манга \"{manga_title}\" скачана в:\n{folder_path}")
                              
        self.scan_library(self.config["root_dir"])
    
    def download_error(self, error_msg):
        self.progress_dialog.close()
        QMessageBox.critical(self, "Ошибка", f"Не удалось скачать:\n{error_msg}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
                                                                  
    icon_path = os.path.join(DATA_DIR, "icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())