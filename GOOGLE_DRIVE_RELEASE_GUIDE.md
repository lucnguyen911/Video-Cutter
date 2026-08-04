# Phát hành cập nhật bằng Google Drive

## Phạm vi

Từ bản **1.0.4**, updater chấp nhận link chia sẻ Google Drive (dạng `/file/d/<FILE_ID>/view` hoặc `open?id=<FILE_ID>`). Ứng dụng tự lấy `FILE_ID`, tải file thật, xử lý trang xác nhận đối với file lớn, rồi chỉ chạy installer nếu cả ba điều kiện đều khớp:

- kích thước (`file_size`) trên Supabase;
- SHA-256 (`sha256`) trên Supabase;
- hai byte đầu của file là `MZ` (Windows executable).

Không đặt access token, mật khẩu Google hoặc API key Google Drive vào ứng dụng hay Supabase.

> Google Drive là nơi lưu trữ tiện lợi cho lượng người dùng nhỏ/vừa, nhưng không phải CDN phát hành phần mềm. Google có thể thay đổi trang xác nhận, giới hạn lưu lượng hoặc chặn file bị gắn cờ. SHA-256 vẫn bảo vệ tính toàn vẹn, nhưng nếu cần tải quy mô lớn/ổn định, nên chuyển sang R2/CDN sau này.

## Quy tắc không được phá vỡ

1. Mỗi bản phát hành phải là **một file mới, một tên mới và một version mới**. Ví dụ: `Video_Cutter_Setup_v1.0.4.exe`.
2. Không upload đè file cũ và không dùng Drive revision cho gói đã phát hành. Link/ID cũ phải giữ nguyên để có thể truy vết.
3. Chỉ cập nhật Supabase sau khi file đã upload hoàn tất, đã bật quyền tải công khai và đã có SHA-256/kích thước chính xác.
4. Không dùng link của thư mục; Supabase phải chứa link của **file `.exe`**.
5. Không tái sử dụng version đã phát hành. Bản có thay đổi tiếp theo là `1.0.5`, không phải một installer `1.0.4` khác.

## Chuẩn bị một lần

1. Cài **Google Drive for desktop** và đăng nhập tài khoản Drive phát hành.
2. Trong My Drive tạo thư mục `Video Cutter Releases`.
3. Đặt chế độ đồng bộ là **Stream files** để không chiếm thêm bản sao toàn bộ Drive trên ổ cứng. Có thể kéo file installer vào thư mục Drive trong File Explorer; Drive for desktop sẽ đồng bộ nền và phù hợp hơn trình duyệt khi file nhiều GB.
4. Chỉ cấp quyền Editor cho người phát hành. Khách hàng không cần quyền thư mục.

Google xác nhận Drive for desktop hỗ trợ Stream/Mirror và tự đồng bộ thay đổi; với file nhiều GB, hãy chờ biểu tượng Drive báo đồng bộ xong trước khi phát hành.

## Quy trình phát hành mỗi version

Ví dụ dưới đây phát hành `1.0.4`.

1. Build installer với `APP_VERSION` và `MyAppVersion` cùng là `1.0.4`.
2. Tính hash và kích thước **trước** khi upload:

```powershell
$installer = 'D:\TOOL MMO\Source code\Video_Cutter\installer_output\Video_Cutter_Setup_v1.0.4.exe'
(Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash
(Get-Item -LiteralPath $installer).Length
```

3. Kéo installer vào `Video Cutter Releases` bằng Google Drive for desktop, hoặc vào `drive.google.com` chọn **New → File upload**. Không đổi tên sau khi hash.
4. Chờ upload hoàn tất. Trên Drive, bấm phải chính file → **Share**:
   - General access: **Anyone with the link**
   - Role: **Viewer**
   - Trong Settings, không tắt quyền tải xuống của Viewer
   - Bấm **Copy link**
5. Dán nguyên link chia sẻ vào cột `download_url`. Không cần tự đổi sang `uc?export=download`; updater 1.0.4 làm việc đó và xử lý xác nhận file lớn.
6. Kiểm tra link bằng cửa sổ ẩn danh. Nó phải mở được không cần đăng nhập Google. Sau đó dùng một máy thử nghiệm cài 1.0.4 để chạy toàn bộ luồng tải/cập nhật trước khi ép buộc người dùng.
7. Chỉ khi test thành công, cập nhật metadata phiên bản trên Supabase.

## Cập nhật Supabase

Thay các giá trị trong ngoặc. Lệnh này **không thay đổi cấu trúc SQL**, chỉ cập nhật metadata của dòng app đang active:

```sql
UPDATE public.app_versions
SET
  latest_version = '1.0.4',
  download_url = '<LINK_CHIA_SE_GOOGLE_DRIVE_CUA_FILE_EXE>',
  sha256 = '<SHA256_64_KY_TU>',
  file_size = <SO_BYTE_CHINH_XAC>,
  package_type = 'full',
  enforcement = 'forced',
  is_active = true,
  published_at = now(),
  changelog = 'Hỗ trợ tải cập nhật ổn định qua Google Drive.'
WHERE app_id = 'video_cutter'
  AND is_active = true;
```

`sha256` phải là 64 ký tự hex, `file_size` là số byte nguyên, không phải MB. Cần có đúng một dòng `is_active = true` cho `video_cutter`.

## Phát hành bản đầu tiên sau thay đổi này

Các bản cũ `1.0.2`/`1.0.3` chưa biết cách vượt trang xác nhận của Google Drive khi file lớn. Vì vậy, để đưa bản sửa này ra ngoài, hãy phân phối installer **1.0.4** một lần qua link Drive thủ công cho người dùng thử nghiệm hoặc dùng một installer 1.0.4 nhỏ đủ để link Drive cũ tải trực tiếp. Sau khi người dùng đã ở 1.0.4, các bản lớn hơn về sau dùng link chia sẻ Drive bình thường.

## Khi lỗi

- Ứng dụng báo trả về HTML: kiểm tra file có đang `Anyone with the link` và người xem được phép tải không.
- Ứng dụng báo hash/kích thước sai: lấy lại hash/kích thước từ file installer gốc; tuyệt đối không thay file trên Drive dưới cùng một version.
- Google cảnh báo file độc hại: không cố vượt cảnh báo. Ký số installer bằng chứng thư Authenticode và gửi yêu cầu Google xem xét nếu đó là false positive.
- Nhiều người không tải được hoặc bị giới hạn: đây là giới hạn vận hành của Drive; chuyển file phát hành sang R2/CDN, không tắt kiểm tra SHA-256 để “sửa” lỗi.