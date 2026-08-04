# Hướng dẫn Biên dịch & Đóng gói Video Cutter v1.0.2

## Mục lục
1. [Chuẩn bị môi trường](#1-chuẩn-bị-môi-trường)
2. [Biên dịch bằng PyInstaller](#2-biên-dịch-bằng-pyinstaller)
3. [Đóng gói bằng Inno Setup](#3-đóng-gói-bằng-inno-setup)
4. [Kiểm tra file Setup](#4-kiểm-tra-file-setup)

---

## 1. Chuẩn bị môi trường

### Yêu cầu phần mềm

| Phần mềm | Phiên bản | Mục đích |
|-----------|-----------|----------|
| Python | 3.11+ | Chạy mã nguồn |
| PyInstaller | 6.20+ | Biên dịch thành .exe |
| Inno Setup | 6.x | Đóng gói thành file cài đặt |

### Cài đặt dependencies

Mở Terminal (PowerShell hoặc CMD) tại thư mục dự án:

```powershell
# Di chuyển tới thư mục dự án
cd "D:\TOOL MMO\Source code\Video_auto_cut"

# Kích hoạt virtual environment (nếu có)
.\.venv\Scripts\Activate.ps1

# Cài đặt các thư viện cần thiết
pip install -r requirements.txt
pip install packaging
```

### Cài đặt Inno Setup

1. Tải Inno Setup tại: https://jrsoftware.org/isdl.php
2. Cài đặt với cấu hình mặc định
3. Đảm bảo đường dẫn `C:\Program Files (x86)\Inno Setup 6\ISCC.exe` tồn tại

---

## 2. Biên dịch bằng PyInstaller

### Cách 1: Dùng file .spec (Khuyến nghị)

File `Video_Cutter.spec` đã được cấu hình sẵn với chế độ `--onedir`. Chỉ cần chạy:

```powershell
# Tại thư mục dự án
pyinstaller Video_Cutter.spec --clean
```

### Cách 2: Dùng lệnh trực tiếp

Nếu muốn build thủ công mà không dùng file `.spec`:

```powershell
pyinstaller main.py `
    --name "Video_Cutter" `
    --onedir `
    --windowed `
    --icon "icon_scissors.ico" `
    --add-data "icon_scissors.ico;." `
    --add-data "assets;assets" `
    --hidden-import "packaging" `
    --hidden-import "packaging.version" `
    --clean
```

### Giải thích tham số

| Tham số | Ý nghĩa |
|---------|---------|
| `--name "Video_Cutter"` | Đặt tên file exe và thư mục đầu ra |
| `--onedir` | Tạo thư mục chứa exe + dependencies (dễ patching) |
| `--windowed` | Ẩn cửa sổ console khi chạy app |
| `--icon "icon_scissors.ico"` | Gán icon cho file exe |
| `--add-data "assets;assets"` | Copy thư mục assets vào bundle |
| `--hidden-import "packaging"` | Import ẩn cho module updater |
| `--clean` | Xóa cache build cũ |

### Kết quả build

Sau khi build thành công, thư mục output sẽ có cấu trúc:

```
dist/
└── Video_Cutter/
    ├── Video_Cutter.exe        ← File chạy chính
    ├── icon_scissors.ico
    ├── assets/
    │   ├── arrow_down.svg
    │   ├── moon.svg
    │   ├── sun.svg
    │   └── ...
    ├── _internal/              ← Dependencies (PyQt6, Python, etc.)
    │   ├── PyQt6/
    │   └── ...
    └── ...
```

### Kiểm tra nhanh

```powershell
# Chạy thử exe đã build
.\dist\Video_Cutter\Video_Cutter.exe
```

Đảm bảo:
- ✅ App hiện lên bình thường (không có cửa sổ console)
- ✅ Dialog nhập License Key hiển thị đúng (nếu chưa kích hoạt)
- ✅ Icon trên thanh taskbar đúng
- ✅ Giao diện (theme, assets) load đầy đủ

---

## 3. Đóng gói bằng Inno Setup

### Cách 1: Dùng Inno Setup GUI

1. Mở **Inno Setup Compiler** (tìm trong Start Menu)
2. File → Open → chọn file `setup_script.iss` trong thư mục dự án
3. Nhấn **Ctrl+F9** hoặc Build → Compile để biên dịch
4. File setup sẽ được tạo tại: `installer_output/Video_Cutter_Setup_v1.0.2.exe`

### Cách 2: Dùng dòng lệnh

```powershell
# Biên dịch trực tiếp từ Terminal
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" setup_script.iss
```

### Kết quả đóng gói

```
installer_output/
└── Video_Cutter_Setup_v1.0.2.exe    ← File setup duy nhất (~50-80 MB)
```

---

## 4. Kiểm tra file Setup

### Checklist kiểm tra trên máy sạch (hoặc VM)

| # | Mục kiểm tra | Kết quả mong đợi |
|---|---|---|
| 1 | Double-click file setup | Hiện wizard cài đặt với icon đúng |
| 2 | Chọn thư mục cài đặt | Mặc định: `C:\Program Files\Video Cutter\` |
| 3 | Tùy chọn Desktop shortcut | Checkbox đã được tích sẵn |
| 4 | Hoàn tất cài đặt | App tự chạy nếu chọn "Launch Video Cutter" |
| 5 | Shortcut Desktop | Icon scissors hiển thị đúng (không phải "tờ giấy trắng") |
| 6 | Start Menu | Có nhóm "Video Cutter" với shortcut app (icon đúng) + uninstall |
| 7 | Chạy ứng dụng | License dialog hiện đúng → nhập key → app chạy OK |
| 8 | Kiểm tra update | App gọi API kiểm tra bản mới khi khởi chạy |
| 9 | Gỡ cài đặt | Control Panel → Uninstall → xóa sạch file + shortcut |

---

## Quy trình release tổng hợp (Tóm tắt)

```
┌──────────────────────────────┐
│  1. Cập nhật CURRENT_VERSION │ ← Sửa trong updater.py
│     trong updater.py         │
├──────────────────────────────┤
│  2. Build PyInstaller        │ ← pyinstaller Video_Cutter.spec --clean
│                              │
├──────────────────────────────┤
│  3. Test thư mục dist/       │ ← Chạy Video_Cutter.exe
│                              │
├──────────────────────────────┤
│  4. Build Inno Setup         │ ← ISCC.exe setup_script.iss
│                              │
├──────────────────────────────┤
│  5. Test file setup          │ ← Cài trên máy sạch
│                              │
├──────────────────────────────┤
│  6. Upload lên GitHub Release│ ← Tạo tag version + đính kèm
│     + cập nhật bảng          │   .exe setup & .zip update
│     app_versions trên        │
│     Supabase                 │
└──────────────────────────────┘
```

> **Lưu ý quan trọng:** Khi phát hành bản mới, nhớ:
> 1. Đổi `CURRENT_VERSION` trong `updater.py` thành version mới
> 2. Đổi `#define MyAppVersion` trong `setup_script.iss` thành version mới
> 3. Upload file `.zip` (nội dung thư mục `dist/Video_Cutter/`) lên GitHub Release
> 4. Cập nhật cột `latest_version` và `download_url` trong bảng `app_versions` trên Supabase
