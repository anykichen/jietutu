# -*- coding: utf-8 -*-
"""
SnapFloat 截图工具
功能：
  - 局部截图 / 全屏截图
  - 截图悬浮于所有窗口之上（可拖动/缩放）
  - 截图内容复制到剪贴板
  - 关闭截图窗口后最小化到系统托盘
  - 右键托盘 -> 退出 才真正退出
  - 鼠标悬停/左键点击托盘图标弹出快捷菜单
  - 开机自启动
  - 单实例运行

Windows 依赖：
  pip install PyQt5 pywin32 Pillow
"""

import sys
import os
import time
import ctypes
from ctypes import wintypes

# ──────────────── 单实例互斥锁（必须在 QApplication 之前） ────────────────
MUTEX_NAME = "SnapFloat_SingleInstance_2025"
_mutex_handle = None

def _acquire_single_instance():
    global _mutex_handle
    _mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    err = ctypes.windll.kernel32.GetLastError()
    ERROR_ALREADY_EXISTS = 183
    return err != ERROR_ALREADY_EXISTS

# ──────────────── Qt 导入 ────────────────
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QSystemTrayIcon, QMenu, QAction, QScrollArea,
    QDesktopWidget, QMessageBox, QFrame, QTextEdit, QDialog,
    QFileDialog, QSizeGrip
)
from PyQt5.QtCore import Qt, QRect, QPoint, QSize, QTimer, pyqtSignal, QThread
from PyQt5.QtGui import (
    QPixmap, QPainter, QPen, QColor, QCursor, QIcon,
    QFont, QImage, QBrush, QLinearGradient, QPalette
)

APP_NAME   = "SnapFloat截图工具"
APP_VER    = "1.0.0"
REG_PATH   = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_KEY    = "SnapFloat"


# ══════════════════════════════════════════════════════════════════════
#  工具函数
# ══════════════════════════════════════════════════════════════════════
def set_autostart(enable: bool) -> bool:
    try:
        import winreg
        exe = (sys.executable if not getattr(sys, "frozen", False)
               else sys.executable)
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0,
                           winreg.KEY_SET_VALUE)
        if enable:
            winreg.SetValueEx(k, REG_KEY, 0, winreg.REG_SZ, f'"{exe}"')
        else:
            try:
                winreg.DeleteValue(k, REG_KEY)
            except FileNotFoundError:
                pass
        winreg.CloseKey(k)
        return True
    except Exception as e:
        print(f"自启动设置失败: {e}")
        return False


def get_autostart() -> bool:
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0,
                           winreg.KEY_READ)
        winreg.QueryValueEx(k, REG_KEY)
        winreg.CloseKey(k)
        return True
    except:
        return False


def make_app_icon(size=64) -> QIcon:
    """生成内置相机图标"""
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)

    # 圆形背景渐变
    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0, QColor("#0078d4"))
    grad.setColorAt(1, QColor("#005a9e"))
    p.setBrush(QBrush(grad))
    p.setPen(Qt.NoPen)
    p.drawEllipse(1, 1, size-2, size-2)

    # 相机主体
    p.setBrush(QBrush(QColor(255, 255, 255, 220)))
    p.drawRoundedRect(size//6, size//3, size*2//3, size*5//12, 4, 4)

    # 镜头
    p.setBrush(QBrush(QColor("#003f8a")))
    cx, cy, cr = size//2, size//2 + size//14, size//6
    p.drawEllipse(cx-cr, cy-cr, cr*2, cr*2)
    p.setBrush(QBrush(QColor("#90caf9")))
    sr = size//12
    p.drawEllipse(cx-sr, cy-sr, sr*2, sr*2)

    # 取景器小方块
    p.setBrush(QBrush(QColor(255, 220, 0)))
    p.drawRoundedRect(size*2//5, size//4, size//5, size//7, 2, 2)

    p.end()
    return QIcon(QPixmap.fromImage(img))


MENU_STYLE = """
QMenu {
    background: #1e1e2e;
    border: 1px solid #334;
    border-radius: 10px;
    padding: 6px 2px;
    font-family: 微软雅黑;
    font-size: 13px;
    color: #dde;
}
QMenu::item {
    padding: 9px 28px 9px 14px;
    border-radius: 6px;
    margin: 1px 4px;
}
QMenu::item:selected  { background: #0078d4; color: #fff; }
QMenu::item:disabled  { color: #666; }
QMenu::separator {
    height: 1px;
    background: #334;
    margin: 4px 10px;
}
"""

BTN_BASE = """
QPushButton {{
    background: {bg};
    color: {fg};
    border: none;
    border-radius: 5px;
    padding: {pad};
    font-family: 微软雅黑;
    font-size: {fs}px;
    font-weight: {fw};
}}
QPushButton:hover   {{ background: {hover}; }}
QPushButton:pressed {{ background: {press}; }}
"""


def make_btn(text, bg="#0078d4", fg="#fff", hover="#106ebe", press="#004f9a",
             pad="7px 18px", fs=13, fw="normal", tip=""):
    b = QPushButton(text)
    b.setStyleSheet(BTN_BASE.format(
        bg=bg, fg=fg, hover=hover, press=press, pad=pad, fs=fs, fw=fw))
    if tip:
        b.setToolTip(tip)
    return b


# ══════════════════════════════════════════════════════════════════════
#  截图选区覆盖层
# ══════════════════════════════════════════════════════════════════════
class ScreenshotOverlay(QWidget):
    screenshot_taken = pyqtSignal(QPixmap)
    cancelled        = pyqtSignal()

    def __init__(self, screen_pixmap: QPixmap):
        super().__init__()
        self.screen_pixmap = screen_pixmap
        self.start_pos = None
        self.end_pos   = None
        self.selecting = False
        self.sel_rect  = QRect()

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)

        # 覆盖全部屏幕（多显示器友好）
        geo = QDesktopWidget().screenGeometry()
        self.setGeometry(geo)
        self.showFullScreen()

        # 提示条
        self.hint = QLabel(
            "  🖱  拖拽选区   ✔ Enter / 双击 确认   ✖ ESC 取消  ", self
        )
        self.hint.setStyleSheet("""
            QLabel {
                background: rgba(0,0,0,175);
                color: #fff;
                padding: 7px 18px;
                border-radius: 8px;
                font-size: 14px;
                font-family: 微软雅黑;
            }
        """)
        self.hint.adjustSize()
        self.hint.move((geo.width() - self.hint.width()) // 2, geo.height() - 56)

        # 选区尺寸标签
        self.size_lbl = QLabel("", self)
        self.size_lbl.setStyleSheet("""
            QLabel {
                background: rgba(0,120,215,210);
                color: #fff;
                padding: 3px 8px;
                border-radius: 4px;
                font-size: 12px;
                font-family: 微软雅黑;
            }
        """)
        self.size_lbl.hide()

    # ── 事件 ──────────────────────────────────────────────
    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.cancelled.emit()
            self.close()
        elif e.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._confirm()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.start_pos = e.pos()
            self.end_pos   = e.pos()
            self.selecting = True

    def mouseMoveEvent(self, e):
        if self.selecting:
            self.end_pos  = e.pos()
            self.sel_rect = QRect(self.start_pos, self.end_pos).normalized()
            self._update_size_label(e.pos())
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.selecting:
            self.selecting = False
            self.end_pos   = e.pos()
            self.sel_rect  = QRect(self.start_pos, self.end_pos).normalized()
            if self.sel_rect.width() > 5 and self.sel_rect.height() > 5:
                self._confirm()

    def mouseDoubleClickEvent(self, e):
        if self.sel_rect.width() > 5:
            self._confirm()

    def _update_size_label(self, pos):
        self.size_lbl.setText(f" {self.sel_rect.width()} × {self.sel_rect.height()} ")
        self.size_lbl.adjustSize()
        x, y = pos.x() + 14, pos.y() - 30
        if x + self.size_lbl.width() > self.width():
            x = pos.x() - self.size_lbl.width() - 14
        if y < 0:
            y = pos.y() + 14
        self.size_lbl.move(x, y)
        self.size_lbl.show()

    def _confirm(self):
        r = self.sel_rect
        if r.width() > 4 and r.height() > 4:
            cropped = self.screen_pixmap.copy(r)
            self.close()
            self.screenshot_taken.emit(cropped)
        else:
            self.cancelled.emit()
            self.close()

    def paintEvent(self, _):
        p = QPainter(self)
        # 底图
        p.drawPixmap(0, 0, self.screen_pixmap)
        # 遮罩
        p.fillRect(self.rect(), QColor(0, 0, 0, 110))
        if not self.sel_rect.isEmpty():
            # 选区内还原
            p.drawPixmap(self.sel_rect, self.screen_pixmap, self.sel_rect)
            # 选区边框
            pen = QPen(QColor("#00b4ff"), 2)
            pen.setStyle(Qt.SolidLine)
            p.setPen(pen)
            p.drawRect(self.sel_rect)
            # 四角锚点
            c = QColor("#00b4ff")
            asz = 10
            for cx, cy in [
                (self.sel_rect.left(),          self.sel_rect.top()),
                (self.sel_rect.right()-asz,     self.sel_rect.top()),
                (self.sel_rect.left(),          self.sel_rect.bottom()-asz),
                (self.sel_rect.right()-asz,     self.sel_rect.bottom()-asz),
            ]:
                p.fillRect(cx, cy, asz, asz, c)


# ══════════════════════════════════════════════════════════════════════
#  悬浮截图窗口
# ══════════════════════════════════════════════════════════════════════
class FloatingWindow(QWidget):
    """悬浮于所有窗口之上的截图预览，支持拖动/缩放/复制"""
    closed_signal = pyqtSignal(object)   # 发送 self

    def __init__(self, pixmap: QPixmap):
        super().__init__()
        self.pixmap       = pixmap
        self._drag_pos    = None
        self._resizing    = False
        self._res_start   = None
        self._res_size    = None

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setMinimumSize(120, 90)

        self._build_ui()
        self._init_size_pos()

    # ── UI 构建 ────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 标题栏 ──
        self.title_bar = QFrame()
        self.title_bar.setFixedHeight(34)
        self.title_bar.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #111827, stop:1 #1e3a5f);
                border-top-left-radius: 9px;
                border-top-right-radius: 9px;
            }
        """)
        tl = QHBoxLayout(self.title_bar)
        tl.setContentsMargins(8, 0, 6, 0)
        tl.setSpacing(5)

        ico = QLabel("📸")
        ico.setStyleSheet("background:transparent; color:#fff; font-size:15px;")
        tl.addWidget(ico)

        self.title_lbl = QLabel(f"截图  {self.pixmap.width()}×{self.pixmap.height()} px")
        self.title_lbl.setStyleSheet(
            "background:transparent; color:#cdd; font-size:12px; font-family:微软雅黑;"
        )
        tl.addWidget(self.title_lbl, 1)

        def icon_btn(icon, tip):
            b = QPushButton(icon)
            b.setFixedSize(28, 28)
            b.setToolTip(tip)
            b.setStyleSheet("""
                QPushButton {
                    background: transparent; color: #bbc; border: none;
                    font-size: 14px; border-radius: 5px;
                }
                QPushButton:hover { background: rgba(255,255,255,35); color:#fff; }
            """)
            return b

        self.btn_copy  = icon_btn("📋", "复制截图到剪贴板 (Ctrl+C)")
        self.btn_text  = icon_btn("📝", "查看文字 / 手动复制")
        self.btn_save  = icon_btn("💾", "另存为图片文件")
        self.btn_pin   = icon_btn("📌", "已置顶 – 点击取消")
        self.btn_close = QPushButton("✕")
        self.btn_close.setFixedSize(28, 28)
        self.btn_close.setToolTip("关闭截图（隐藏到托盘）")
        self.btn_close.setStyleSheet("""
            QPushButton {
                background: transparent; color: #bbc; border: none;
                font-size: 13px; border-radius: 5px;
            }
            QPushButton:hover { background: #c0392b; color: #fff; }
        """)

        for b in (self.btn_copy, self.btn_text, self.btn_save, self.btn_pin, self.btn_close):
            tl.addWidget(b)

        root.addWidget(self.title_bar)

        # ── 图片区 ──
        self.img_frame = QFrame()
        self.img_frame.setStyleSheet("""
            QFrame {
                background: #121826;
                border: 1px solid #1e3a5f;
                border-top: none;
            }
        """)
        il = QVBoxLayout(self.img_frame)
        il.setContentsMargins(3, 3, 3, 3)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")

        self.img_lbl = QLabel()
        self.img_lbl.setAlignment(Qt.AlignCenter)
        self.img_lbl.setStyleSheet("background:transparent;")
        self.scroll.setWidget(self.img_lbl)
        il.addWidget(self.scroll)
        root.addWidget(self.img_frame, 1)

        # ── 状态栏 + 缩放手柄 ──
        bot = QFrame()
        bot.setFixedHeight(22)
        bot.setStyleSheet("""
            QFrame {
                background:#0d1b2a;
                border: 1px solid #1e3a5f;
                border-top: none;
                border-bottom-left-radius: 9px;
                border-bottom-right-radius: 9px;
            }
        """)
        bl = QHBoxLayout(bot)
        bl.setContentsMargins(8, 0, 2, 0)
        bl.setSpacing(0)

        self.status_lbl = QLabel("  拖动标题栏移动  |  右下角拖动缩放")
        self.status_lbl.setStyleSheet(
            "color:#556; font-size:11px; font-family:微软雅黑; background:transparent;"
        )
        bl.addWidget(self.status_lbl, 1)

        self.grip = QSizeGrip(self)
        self.grip.setStyleSheet("background:transparent;")
        bl.addWidget(self.grip, 0, Qt.AlignRight | Qt.AlignBottom)

        root.addWidget(bot)

        # ── 信号连接 ──
        self.btn_copy.clicked.connect(self.copy_image)
        self.btn_text.clicked.connect(self.show_text_dialog)
        self.btn_save.clicked.connect(self.save_image)
        self.btn_pin.clicked.connect(self.toggle_pin)
        self.btn_close.clicked.connect(self._on_close)

        self._is_pinned = True

        # Ctrl+C 快捷键
        from PyQt5.QtWidgets import QShortcut
        from PyQt5.QtGui import QKeySequence
        QShortcut(QKeySequence("Ctrl+C"), self, self.copy_image)

    def _init_size_pos(self):
        max_w = min(self.pixmap.width() + 16,  900)
        max_h = min(self.pixmap.height() + 70, 650)
        self.resize(max(220, max_w), max(160, max_h))
        self._refresh_image()
        # 屏幕右上方
        sc = QDesktopWidget().screenGeometry()
        self.move(sc.width() - self.width() - 24, 80)

    def _refresh_image(self):
        aw = self.scroll.viewport().width()
        ah = self.scroll.viewport().height()
        if aw < 10 or ah < 10:
            self.img_lbl.setPixmap(self.pixmap)
            return
        scaled = self.pixmap.scaled(aw, ah, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.img_lbl.setPixmap(scaled)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        QTimer.singleShot(30, self._refresh_image)

    # ── 操作 ────────────────────────────────────────────
    def copy_image(self):
        QApplication.clipboard().setPixmap(self.pixmap)
        self._set_status("✓ 截图已复制到剪贴板！", 2500)

    def save_image(self):
        ts   = time.strftime("%Y%m%d_%H%M%S")
        name = f"截图_{ts}.png"
        path, _ = QFileDialog.getSaveFileName(
            self, "保存截图", name,
            "PNG 图片 (*.png);;JPEG 图片 (*.jpg *.jpeg);;所有文件 (*)"
        )
        if path:
            self.pixmap.save(path)
            self._set_status(f"✓ 已保存：{path}", 3500)

    def show_text_dialog(self):
        dlg = TextCopyDialog(self.pixmap, self)
        dlg.exec_()

    def toggle_pin(self):
        self._is_pinned = not self._is_pinned
        flags = Qt.FramelessWindowHint | Qt.Tool
        if self._is_pinned:
            flags |= Qt.WindowStaysOnTopHint
            self.btn_pin.setToolTip("已置顶 – 点击取消")
            self.btn_pin.setText("📌")
        else:
            self.btn_pin.setToolTip("未置顶 – 点击置顶")
            self.btn_pin.setText("🔓")
        self.setWindowFlags(flags)
        self.show()

    def _set_status(self, msg, ms=2500):
        self.status_lbl.setText("  " + msg)
        QTimer.singleShot(ms, lambda: self.status_lbl.setText(
            "  拖动标题栏移动  |  右下角拖动缩放"
        ))

    def _on_close(self):
        self.hide()
        self.closed_signal.emit(self)

    # ── 鼠标拖动 ────────────────────────────────────────────
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            if self.title_bar.geometry().contains(e.pos()):
                self._drag_pos = e.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.LeftButton and self._drag_pos:
            if self.title_bar.geometry().contains(e.pos()) or self._drag_pos:
                self.move(e.globalPos() - self._drag_pos)

    def mouseReleaseEvent(self, e):
        self._drag_pos = None


# ══════════════════════════════════════════════════════════════════════
#  文字复制对话框
# ══════════════════════════════════════════════════════════════════════
class TextCopyDialog(QDialog):
    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self.pixmap = pixmap
        self.setWindowTitle("截图内容 – 文字复制")
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint)
        self.resize(720, 520)
        self.setStyleSheet("""
            QDialog  { background:#1a1b2e; }
            QLabel   { color:#dde; font-family:微软雅黑; }
            QTextEdit{
                background:#252640; color:#eef; border:1px solid #334;
                border-radius:6px; font-family:微软雅黑; font-size:13px; padding:5px;
            }
            QScrollBar:vertical   { width:8px; background:#1a1b2e; }
            QScrollBar::handle:vertical { background:#334; border-radius:4px; }
        """)

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.setContentsMargins(14, 14, 14, 12)

        # 提示
        tip = QLabel(
            "📌  预览截图图片。如需复制截图中的文字：\n"
            "① 在下方文本框手动输入文字后点击「复制文字」；\n"
            "② 或点击「复制图片」把截图放入剪贴板后，粘贴到支持OCR的应用（如 Word / OneNote / 微信）。"
        )
        tip.setStyleSheet("color:#99a; font-size:12px; font-family:微软雅黑; line-height:160%;")
        tip.setWordWrap(True)
        lay.addWidget(tip)

        # 图片预览
        preview = QLabel()
        scaled  = pixmap.scaled(680, 280, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        preview.setPixmap(scaled)
        preview.setAlignment(Qt.AlignCenter)
        preview.setStyleSheet("background:#252640; border-radius:6px; padding:6px;")
        lay.addWidget(preview)

        # 文字区
        lbl2 = QLabel("✏️  输入截图中的文字（手动），然后复制：")
        lbl2.setStyleSheet("color:#bbc; font-size:12px; font-family:微软雅黑;")
        lay.addWidget(lbl2)

        self.te = QTextEdit()
        self.te.setPlaceholderText("在此输入截图中的文字…")
        self.te.setFixedHeight(80)
        lay.addWidget(self.te)

        # 按钮行
        br = QHBoxLayout()
        br.setSpacing(8)

        b1 = make_btn("📋  复制文字",  tip="将文本框中的内容复制到剪贴板")
        b2 = make_btn("🖼️  复制图片",
                      bg="#107c10", hover="#0e6b0e", press="#0c5c0c",
                      tip="将截图图片复制到剪贴板")
        b3 = make_btn("关闭", bg="#444", hover="#333", press="#222")

        b1.clicked.connect(self._copy_text)
        b2.clicked.connect(self._copy_img)
        b3.clicked.connect(self.accept)

        br.addWidget(b1)
        br.addWidget(b2)
        br.addStretch()
        br.addWidget(b3)
        lay.addLayout(br)

    def _copy_text(self):
        txt = self.te.toPlainText().strip()
        if txt:
            QApplication.clipboard().setText(txt)
            QMessageBox.information(self, "成功", "✓ 文字已复制到剪贴板！")
        else:
            QMessageBox.warning(self, "提示", "文本框为空，请先输入文字。")

    def _copy_img(self):
        QApplication.clipboard().setPixmap(self.pixmap)
        QMessageBox.information(self, "成功", "✓ 截图已复制到剪贴板！")
        self.accept()


# ══════════════════════════════════════════════════════════════════════
#  系统托盘
# ══════════════════════════════════════════════════════════════════════
class AppTray(QSystemTrayIcon):
    def __init__(self, app: "SnapFloatApp"):
        super().__init__(make_app_icon())
        self.app = app
        self.setToolTip(f"📸 {APP_NAME}\n左键 – 快捷操作\n右键 – 更多菜单")
        self._build_context_menu()
        self.activated.connect(self._on_activated)

    def _build_context_menu(self):
        m = QMenu()
        m.setStyleSheet(MENU_STYLE)

        # 标题（不可点击）
        title_act = QAction(f"📸  {APP_NAME}  v{APP_VER}", m)
        title_act.setEnabled(False)
        m.addAction(title_act)
        m.addSeparator()

        # 截图
        a1 = QAction("✂️    截取局部区域       Ctrl+Alt+A", m)
        a1.triggered.connect(self.app.start_region_shot)
        m.addAction(a1)

        a2 = QAction("🖥️    截取全屏           Ctrl+Alt+F", m)
        a2.triggered.connect(self.app.take_fullscreen)
        m.addAction(a2)

        m.addSeparator()

        # 窗口管理
        a3 = QAction("📂  显示全部截图窗口", m)
        a3.triggered.connect(self.app.show_all)
        m.addAction(a3)

        a4 = QAction("🙈  隐藏全部截图窗口", m)
        a4.triggered.connect(self.app.hide_all)
        m.addAction(a4)

        a5 = QAction("🗑️    关闭全部截图窗口", m)
        a5.triggered.connect(self.app.close_all)
        m.addAction(a5)

        m.addSeparator()

        # 自启动
        self.act_auto = QAction("🚀  开机自动启动", m)
        self.act_auto.setCheckable(True)
        self.act_auto.setChecked(get_autostart())
        self.act_auto.triggered.connect(self._toggle_auto)
        m.addAction(self.act_auto)

        m.addSeparator()

        a_about = QAction("ℹ️    关于 SnapFloat", m)
        a_about.triggered.connect(self._about)
        m.addAction(a_about)

        m.addSeparator()

        a_exit = QAction("❌  退出程序", m)
        a_exit.triggered.connect(self.app.quit)
        m.addAction(a_exit)

        self.setContextMenu(m)
        self._ctx_menu = m

    def _toggle_auto(self):
        ok = set_autostart(self.act_auto.isChecked())
        if ok:
            s = "已开启" if self.act_auto.isChecked() else "已关闭"
            self.showMessage(APP_NAME, f"✓ 开机自启动{s}", QSystemTrayIcon.Information, 2000)
        else:
            self.act_auto.setChecked(not self.act_auto.isChecked())
            self.showMessage(APP_NAME, "⚠️ 设置失败，请以管理员身份运行", QSystemTrayIcon.Warning, 2000)

    def _about(self):
        QMessageBox.about(
            None, f"关于 {APP_NAME}",
            f"<h3>📸 {APP_NAME}</h3>"
            f"<p>版本：{APP_VER}</p><hr>"
            f"<b>功能简介</b><br>"
            f"• ✂️ 局部截图（拖拽选区）<br>"
            f"• 🖥️ 全屏截图（一键截全屏）<br>"
            f"• 📌 截图悬浮于所有窗口之上<br>"
            f"• 📋 一键复制截图到剪贴板<br>"
            f"• 💾 保存为 PNG / JPG<br>"
            f"• 🚀 开机自动启动<br>"
            f"• 🔒 单实例运行，不重复开启<br><hr>"
            f"<b>快捷键</b><br>"
            f"• Ctrl+Alt+A：局部截图<br>"
            f"• Ctrl+Alt+F：全屏截图<br>"
            f"• ESC：取消选区<br>"
            f"• Ctrl+C（截图窗口内）：复制图片<br>"
        )

    def _on_activated(self, reason):
        """左键单击 → 弹出快捷菜单"""
        if reason == QSystemTrayIcon.Trigger:
            self._show_quick_menu()

    def _show_quick_menu(self):
        count = len(self.app.windows)
        m = QMenu()
        m.setStyleSheet(MENU_STYLE)

        hdr = QAction("📸  SnapFloat 截图工具", m)
        hdr.setEnabled(False)
        m.addAction(hdr)
        m.addSeparator()

        a1 = QAction("✂️  截取局部区域", m)
        a1.triggered.connect(self.app.start_region_shot)
        m.addAction(a1)

        a2 = QAction("🖥️  截取全屏", m)
        a2.triggered.connect(self.app.take_fullscreen)
        m.addAction(a2)

        m.addSeparator()

        a3 = QAction(f"📂  显示全部截图（{count} 张）", m)
        a3.triggered.connect(self.app.show_all)
        a3.setEnabled(count > 0)
        m.addAction(a3)

        a4 = QAction("🗑️  关闭全部截图", m)
        a4.triggered.connect(self.app.close_all)
        a4.setEnabled(count > 0)
        m.addAction(a4)

        m.exec_(QCursor.pos())


# ══════════════════════════════════════════════════════════════════════
#  主应用控制器
# ══════════════════════════════════════════════════════════════════════
class SnapFloatApp:
    def __init__(self):
        self.qapp    = QApplication(sys.argv)
        self.qapp.setApplicationName(APP_NAME)
        self.qapp.setQuitOnLastWindowClosed(False)

        self.windows: list[FloatingWindow] = []
        self.overlay = None

        # 默认开启自启动（首次运行）
        if not get_autostart():
            set_autostart(True)

        # 托盘
        self.tray = AppTray(self)
        self.tray.show()

        # 全局热键
        self._register_hotkeys()

        # 欢迎提示
        self.tray.showMessage(
            APP_NAME,
            "✓ 程序已在系统托盘运行\n"
            "左键单击图标快速截图\n"
            "Ctrl+Alt+A 局部截图  |  Ctrl+Alt+F 全屏截图",
            QSystemTrayIcon.Information, 4000
        )

    # ── 热键 ────────────────────────────────────────────
    def _register_hotkeys(self):
        try:
            MOD_CTRL_ALT = 0x0002 | 0x0004   # MOD_CONTROL | MOD_ALT
            ctypes.windll.user32.RegisterHotKey(None, 1, MOD_CTRL_ALT, 0x41)  # A
            ctypes.windll.user32.RegisterHotKey(None, 2, MOD_CTRL_ALT, 0x46)  # F
            self._hotkey_timer = QTimer()
            self._hotkey_timer.timeout.connect(self._poll_hotkeys)
            self._hotkey_timer.start(80)
        except Exception as e:
            print(f"热键注册失败: {e}")

    def _poll_hotkeys(self):
        try:
            msg = wintypes.MSG()
            if ctypes.windll.user32.PeekMessageW(
                ctypes.byref(msg), None, 0x0312, 0x0312, 1  # WM_HOTKEY
            ):
                if msg.wParam == 1:
                    self.start_region_shot()
                elif msg.wParam == 2:
                    self.take_fullscreen()
        except:
            pass

    # ── 截图 ────────────────────────────────────────────
    def start_region_shot(self):
        """局部截图"""
        # 临时隐藏所有悬浮窗，避免截入
        states = [(w, w.isVisible()) for w in self.windows]
        for w, _ in states:
            w.hide()
        QApplication.processEvents()
        time.sleep(0.18)

        pix = QApplication.primaryScreen().grabWindow(0)

        for w, vis in states:
            if vis:
                w.show()

        self.overlay = ScreenshotOverlay(pix)
        self.overlay.screenshot_taken.connect(self._on_screenshot)
        self.overlay.cancelled.connect(lambda: None)

    def take_fullscreen(self):
        """全屏截图"""
        for w in self.windows:
            w.hide()
        QApplication.processEvents()
        time.sleep(0.22)

        pix = QApplication.primaryScreen().grabWindow(0)

        for w in self.windows:
            w.show()

        self._on_screenshot(pix)

    def _on_screenshot(self, pix: QPixmap):
        fw = FloatingWindow(pix)
        fw.closed_signal.connect(self._on_win_closed)
        self.windows.append(fw)
        fw.show()
        self.tray.showMessage(
            "截图成功",
            f"已截取 {pix.width()}×{pix.height()} px，悬浮显示于所有窗口之上",
            QSystemTrayIcon.Information, 1800
        )

    def _on_win_closed(self, win):
        if win in self.windows:
            self.windows.remove(win)

    # ── 窗口管理 ────────────────────────────────────────────
    def show_all(self):
        for w in self.windows:
            w.show()
            w.raise_()

    def hide_all(self):
        for w in self.windows:
            w.hide()

    def close_all(self):
        for w in list(self.windows):
            w.close()
        self.windows.clear()

    # ── 退出 ────────────────────────────────────────────
    def quit(self):
        try:
            ctypes.windll.user32.UnregisterHotKey(None, 1)
            ctypes.windll.user32.UnregisterHotKey(None, 2)
        except:
            pass
        self.tray.hide()
        self.qapp.quit()

    def run(self):
        sys.exit(self.qapp.exec_())


# ══════════════════════════════════════════════════════════════════════
#  程序入口
# ══════════════════════════════════════════════════════════════════════
def main():
    # DPI 感知
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except:
            pass

    # 单实例检查
    if not _acquire_single_instance():
        ctypes.windll.user32.MessageBoxW(
            0,
            "SnapFloat截图工具已经在运行！\n请查看右下角系统托盘区域。",
            "提示",
            0x40 | 0x1000
        )
        sys.exit(0)

    app = SnapFloatApp()
    app.run()


if __name__ == "__main__":
    main()
