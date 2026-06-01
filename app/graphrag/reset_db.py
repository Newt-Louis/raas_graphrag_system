import shutil
from pathlib import Path

DATA_DIR = Path("app/data")
LANCEDB_PATH = DATA_DIR / "lancedb"
KUZU_PATH = DATA_DIR / "kuzu"

def clean_directory(dir_path: Path):
    if dir_path.exists() and dir_path.is_dir():
        try:
            shutil.rmtree(dir_path)
            print(f"Đã xóa sạch dữ liệu tại: {dir_path}")
        except Exception as e:
            print(f"Lỗi khi xóa {dir_path}: {e}\n(Hãy đảm bảo đã tắt server trước khi chạy script!)")
    else:
        print(f"⚠️ Thư mục không tồn tại (đã sạch): {dir_path}")

if __name__ == "__main__":
    print("Khởi động dọn dẹp Database...")
    clean_directory(LANCEDB_PATH)
    clean_directory(KUZU_PATH)
    print("Hoàn tất! Chạy lại ứng dụng để khởi tạo database mới.")