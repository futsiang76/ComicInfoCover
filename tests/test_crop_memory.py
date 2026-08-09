"""裁剪记忆系统测试（移植自 007 image_handler/crop_memory.py）"""
from processors.crop_memory import CropMemory

# 测试用标准竖版图（1200x1230）：推荐 x=0.2*1200=240 不触边界钳制
W, H = 1200, 1230
ASPECT = W / H


def test_crop_memory_save_and_load(tmp_path):
    """保存经验到文件后重新加载，内容一致"""
    mem_file = tmp_path / "crop_memory.json"
    mem = CropMemory(memory_file=str(mem_file))
    mem.add_experience(ASPECT, (240, 0, 870, 1230), (W, H))
    mem.save_memory()
    assert mem_file.exists()

    mem2 = CropMemory(memory_file=str(mem_file))
    assert mem2.get_experience_count() == 1
    assert abs(mem2.experiences[0].aspect_ratio - ASPECT) < 1e-6
    assert mem2.experiences[0].x_position_ratio == 0.2


def test_crop_memory_recommend_no_experience(tmp_path):
    """无经验时返回 None"""
    mem = CropMemory(memory_file=str(tmp_path / "crop_memory.json"))
    assert mem.get_recommended_crop(W, H, 1.0) is None


def test_crop_memory_recommend_with_experience(tmp_path):
    """有相似比例经验时返回推荐裁剪位置"""
    mem = CropMemory(memory_file=str(tmp_path / "crop_memory.json"))
    mem.add_experience(ASPECT, (240, 0, 870, 1230), (W, H))
    rec = mem.get_recommended_crop(W, H, 1.0)
    assert rec is not None
    x, y, w, h = rec
    assert x == 240
    assert y == 0
    assert w == 870
    assert h == 1230


def test_crop_memory_recommend_clamped_to_bounds(tmp_path):
    """推荐位置超出图片边界时钳制到边界内（继承 007 逻辑）"""
    mem = CropMemory(memory_file=str(tmp_path / "crop_memory.json"))
    mem.add_experience(0.813, (200, 0, 870, 1230), (1000, 1230))
    # 1000 宽图：x=200 越界（crop_width=870 → 最大 x=130），钳制到 130
    rec = mem.get_recommended_crop(1000, 1230, 1.0)
    assert rec[0] == 130


def test_crop_memory_recommend_out_of_tolerance(tmp_path):
    """比例差异超过容差（5%）时不推荐"""
    mem = CropMemory(memory_file=str(tmp_path / "crop_memory.json"))
    mem.add_experience(ASPECT, (240, 0, 870, 1230), (W, H))
    # 横向图 1920/1080=1.778，与 0.9756 差异远超 5%
    assert mem.get_recommended_crop(1920, 1080, 1.0) is None


def test_crop_memory_clear(tmp_path):
    """清空经验"""
    mem = CropMemory(memory_file=str(tmp_path / "crop_memory.json"))
    mem.add_experience(ASPECT, (240, 0, 870, 1230), (W, H))
    mem.clear_memory()
    assert mem.get_experience_count() == 0
