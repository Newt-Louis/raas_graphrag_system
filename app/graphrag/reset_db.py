import shutil
from pathlib import Path

from app.core.config import settings

# Dùng đúng path runtime trong config thay vì hard-code "app/data" (path cũ sai).
LANCEDB_PATH = Path(settings.LANCEDB_PATH)
KUZU_DB_PATH = Path(settings.KUZU_DB_PATH)


def clean_directory_contents(dir_path: Path, *, keep: set[str] = frozenset({".gitkeep"})) -> None:
    """Xóa toàn bộ table/file con nhưng giữ lại thư mục và file đánh dấu như .gitkeep."""
    if not dir_path.exists():
        print(f"⚠️ Thư mục không tồn tại (đã sạch): {dir_path}")
        dir_path.mkdir(parents=True, exist_ok=True)
        return
    removed = 0
    for child in dir_path.iterdir():
        if child.name in keep:
            continue
        try:
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
            removed += 1
        except Exception as exc:
            print(f"Lỗi khi xóa {child}: {exc}\n(Hãy đảm bảo đã tắt server trước khi chạy script!)")
    print(f"Đã xóa {removed} mục trong: {dir_path}")


def clean_path(target: Path) -> None:
    """Xóa một path cụ thể (file hoặc thư mục) như Kuzu graph.db."""
    if not target.exists():
        print(f"⚠️ Không tồn tại (đã sạch): {target}")
        return
    try:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        print(f"Đã xóa: {target}")
    except Exception as exc:
        print(f"Lỗi khi xóa {target}: {exc}\n(Hãy đảm bảo đã tắt server trước khi chạy script!)")


if __name__ == "__main__":
    print("Khởi động dọn dẹp Database...")
    print(f"LanceDB: {LANCEDB_PATH.resolve()}")
    print(f"Kuzu:    {KUZU_DB_PATH.resolve()}")
    # LanceDB: xóa các table con, giữ thư mục + .gitkeep.
    clean_directory_contents(LANCEDB_PATH)
    # Kuzu: xóa file/thư mục graph.db cùng các file lock/wal đi kèm.
    clean_path(KUZU_DB_PATH)
    for suffix in (".wal", ".lock", ".tmp"):
        clean_path(KUZU_DB_PATH.with_name(KUZU_DB_PATH.name + suffix))
    print("Hoàn tất! Tắt server (nếu đang chạy) rồi khởi động lại để khởi tạo database mới.")
