# Hướng dẫn Biên dịch & Đóng gói Video Cutter

## Mục lục
1. [Chuẩn bị môi trường](#1-chuẩn-bị-môi-trường)
2. [Build tự động](#2-build-tự-động-khuyến-nghị)
3. [Build thủ công](#3-build-thủ-công)
4. [Kiểm tra file Setup](#4-kiểm-tra-file-setup)
5. [Quy trình release](#5-quy-trình-release)

---

## 1. Chuẩn bị môi trường

### Yêu cầu phần mềm

| Phần mềm | Phiên bản | Mục đích |
|-----------|-----------|----------|
| Python | 3.11+ | Chạy mã nguồn |
| PyInstaller | 6.20+ | Biên dịch thành .exe |
| Inno Setup | 6.x | Đóng gói thành file cài đặt |

### Cài đặt dependencies

```powershell
# Kích hoạt virtual environment (nếu có)
.\.venv\Scripts\Activate.ps1

# Cài đặt các thư viện cần thiết
pip install -r requirements.txt
```

### Cài đặt Inno Setup

1. Tải Inno Setup tại: https://jrsoftware.org/isdl.php
2. Cài đặt với cấu hình mặc định
3. Đảm bảo đường dẫn `C:\Program Files (x86)\Inno Setup 6\ISCC.exe` tồn tại

---

## 2. Build tự động (Khuyến nghị)

Sử dụng script `build_release.ps1`:

```powershell
.\build_release.ps1
```

Script này sẽ tự động:
1. ✅ Đọc `APP_VERSION` từ `version.py` (nguồn duy nhất)
2. ✅ Xóa build/dist cũ
3. ✅ Chạy PyInstaller bằng `Video_Cutter.spec`
4. ✅ Kiểm tra `Video_Cutter.exe` tồn tại
5. ✅ Chạy Inno Setup với đúng version
6. ✅ Tính SHA-256 và file size
7. ✅ Tạo metadata JSON phục vụ upload

### Thay đổi version

**CHỈ SỬA MỘT FILE DUY NHẤT:** `version.py`

```python
APP_VERSION = "1.0.2"  # ← Sửa ở đây
```

Build script sẽ tự truyền version vào cả PyInstaller và Inno Setup.

> ⚠️ **KHÔNG** sửa version ở `updater.py`, `setup_script.iss`, hay bất kỳ file nào khác.

---

## 3. Build thủ công

### PyInstaller

```powershell
pyinstaller Video_Cutter.spec --clean
```

> **Lưu ý:** Chỉ dùng `Video_Cutter.spec`. Hai file `VideoFactory.spec` và `VideoAutoCut.spec` đã **deprecated**.

### Inno Setup

```powershell
# Truyền version từ dòng lệnh
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /DMyAppVersion=1.0.1 setup_script.iss
```

### Kết quả build

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
    ├── _internal/              ← Dependencies
    └── ...

installer_output/
├── Video_Cutter_Setup_v1.0.1.exe
└── release_metadata.json
```

---

## 4. Kiểm tra file Setup

### Checklist

| # | Mục kiểm tra | Kết quả mong đợi |
|---|---|---|
| 1 | Double-click file setup | Hiện wizard cài đặt với icon đúng |
| 2 | Chọn thư mục cài đặt | Mặc định: `C:\Program Files\Video Cutter\` |
| 3 | Tùy chọn Desktop shortcut | Checkbox đã được tích sẵn |
| 4 | Hoàn tất cài đặt | App tự chạy nếu chọn "Launch" |
| 5 | License dialog | Hiện đúng → nhập key → DPAPI lưu thành công |
| 6 | HWID v2 | Dùng MachineGuid, không đổi khi thêm USB/VPN |
| 7 | Update check | Kiểm tra app_versions trên Supabase |
| 8 | Gỡ cài đặt | Xóa sạch file + shortcut, giữ AppData |

---

## 5. Quy trình release

```
┌──────────────────────────────┐
│  1. Sửa APP_VERSION trong    │ ← version.py (duy nhất)
│     version.py               │
├──────────────────────────────┤
│  2. Chạy build_release.ps1   │ ← PyInstaller + Inno Setup
│                              │
├──────────────────────────────┤
│  3. Test file setup          │ ← Cài trên máy sạch/VM
│                              │
├──────────────────────────────┤
│  4. Upload lên GitHub Release│ ← Đính kèm installer .exe
│                              │
├──────────────────────────────┤
│  5. Cập nhật Supabase        │ ← Dùng metadata từ
│     app_versions             │   release_metadata.json
└──────────────────────────────┘
```

### Cập nhật Supabase `app_versions`

Dùng thông tin từ `installer_output/release_metadata.json`:

```sql
UPDATE app_versions
SET
  latest_version = '1.0.1',
  download_url = 'https://github.com/.../Video_Cutter_Setup_v1.0.1.exe',
  sha256 = '<sha256 from metadata>',
  file_size = <size from metadata>,
  enforcement = 'optional',
  package_type = 'full'
WHERE app_id = 'video_cutter';
```
