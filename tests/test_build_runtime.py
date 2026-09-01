from pathlib import Path

from build_protected import synchronize_msvc_runtime


def test_synchronize_msvc_runtime_replaces_older_python_copy(tmp_path: Path):
    internal = tmp_path / "Video_Cutter" / "_internal"
    qt_bin = internal / "PyQt6" / "Qt6" / "bin"
    qt_bin.mkdir(parents=True)
    (internal / "VCRUNTIME140.dll").write_bytes(b"old-python-runtime")
    (qt_bin / "vcruntime140.dll").write_bytes(b"new-qt-runtime")
    (qt_bin / "msvcp140.dll").write_bytes(b"matching-msvcp")

    copied = synchronize_msvc_runtime(tmp_path / "Video_Cutter")

    assert "vcruntime140.dll" in copied
    assert "msvcp140.dll" in copied
    assert (internal / "VCRUNTIME140.dll").read_bytes() == b"new-qt-runtime"
    assert (internal / "msvcp140.dll").read_bytes() == b"matching-msvcp"
