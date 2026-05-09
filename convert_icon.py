from PIL import Image

source = "scissors.png"
output = "icon_scissors.ico"

img = Image.open(source).convert("RGBA")

# Cắt sát vùng có hình, bỏ khoảng trống thừa
bbox = img.getbbox()
if bbox:
    img = img.crop(bbox)

# Đặt lại vào canvas vuông trong suốt
size = max(img.size)
canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
x = (size - img.width) // 2
y = (size - img.height) // 2
canvas.paste(img, (x, y), img)

canvas.save(
    output,
    format="ICO",
    sizes=[
        (16, 16),
        (24, 24),
        (32, 32),
        (48, 48),
        (64, 64),
        (128, 128),
        (256, 256),
    ],
)

print(f"Đã tạo {output}")