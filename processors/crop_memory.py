"""
智能裁剪记忆模块
功能：记录和管理不同比例图片的裁剪经验，实现智能推荐
（移植自 007_zipCoverCropper/image_handler/crop_memory.py，逻辑不变）
"""

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class CropExperience:
    """单次裁剪经验（简化版，只记录关键参数）"""
    aspect_ratio: float      # 原图长宽比
    x_position_ratio: float  # 左上角顶点在图片长度上的比例关系（0.0-1.0）
    timestamp: float         # 时间戳

class CropMemory:
    """裁剪记忆管理器"""

    def __init__(self, memory_file=None):
        """初始化裁剪记忆"""
        if memory_file is None:
            # 将记忆文件保存到 memory 目录
            self.memory_file = Path(__file__).parent.parent / "memory" / "crop_memory.json"
        else:
            self.memory_file = Path(memory_file)

        # 经验存储
        self.experiences: List[CropExperience] = []

        # 比例容差（用于相似度匹配）
        self.aspect_ratio_tolerance = 0.05  # 5%的容差

        # 最大经验数量限制
        self.max_experiences = 10000  # 限制最多保存10000条经验

        # 加载历史经验
        self.load_memory()

        # 加载后检查并限制经验数量
        self._limit_experiences()

    def load_memory(self):
        """加载历史裁剪经验"""
        if self.memory_file.exists():
            try:
                with open(self.memory_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                self.experiences = []
                for item in data.get('experiences', []):
                    # 直接使用新格式
                    experience = CropExperience(
                        aspect_ratio=item['aspect_ratio'],
                        x_position_ratio=item['x_position_ratio'],
                        timestamp=item['timestamp']
                    )
                    self.experiences.append(experience)

                print(f"加载了 {len(self.experiences)} 条裁剪经验")

            except Exception as e:
                print(f"加载裁剪记忆失败: {e}")
                self.experiences = []
        else:
            self.experiences = []
            print("未找到裁剪记忆文件，将创建新的记忆文件")

    def save_memory(self):
        """保存裁剪经验到文件"""
        try:
            data = {
                'experiences': [asdict(exp) for exp in self.experiences]
            }

            self.memory_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.memory_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            print(f"保存裁剪记忆失败: {e}")

    def _limit_experiences(self):
        """限制经验数量，超过最大值时删除最旧的经验"""
        if len(self.experiences) > self.max_experiences:
            # 按时间戳排序（最旧的在前）
            self.experiences.sort(key=lambda x: x.timestamp)
            # 删除最旧的经验，保留最新的max_experiences条
            self.experiences = self.experiences[-self.max_experiences:]
            print(f"裁剪经验数量超过限制，已保留最新的 {self.max_experiences} 条经验")
            # 保存到文件
            self.save_memory()

    def add_experience(self, aspect_ratio: float, crop_region: Tuple[int, int, int, int],
                      image_size: Tuple[int, int], display_scale: float = 1.0):
        """添加新的裁剪经验（记录纵横比和左上角顶点在缩放后图片长度的比例关系）"""
        import time

        crop_x, crop_y, crop_width, crop_height = crop_region
        image_width, image_height = image_size

        # 计算缩放后的图片长度
        scaled_image_width = image_width * display_scale

        # 计算红框左上顶点在缩放后图片长度上的百分比（保留3位小数）
        x_position_ratio = round(crop_x * display_scale / scaled_image_width, 3) if scaled_image_width > 0 else 0.0

        experience = CropExperience(
            aspect_ratio=aspect_ratio,
            x_position_ratio=x_position_ratio,  # 记录水平位置比例（缩放后）
            timestamp=time.time()
        )

        # 添加到经验列表
        self.experiences.append(experience)

        # 检查并限制经验数量
        self._limit_experiences()

        print(f"新增裁剪经验: 比例 {aspect_ratio:.3f}, 缩放后水平位置比例 {x_position_ratio:.3f}")

    def find_similar_experience(self, target_aspect_ratio: float) -> Optional[CropExperience]:
        """
        查找相似比例的裁剪经验

        Args:
            target_aspect_ratio: 目标图片的长宽比

        Returns:
            最相似的裁剪经验，如果没有找到返回None
        """
        if not self.experiences:
            return None

        # 按时间倒序排序（最近的优先）
        sorted_experiences = sorted(self.experiences, key=lambda x: x.timestamp, reverse=True)

        # 查找相似比例的经验
        similar_experiences = []

        for exp in sorted_experiences:
            ratio_diff = abs(exp.aspect_ratio - target_aspect_ratio) / target_aspect_ratio

            if ratio_diff <= self.aspect_ratio_tolerance:
                similar_experiences.append((exp, ratio_diff))

        if not similar_experiences:
            return None

        # 返回最相似的经验（比例差异最小）
        similar_experiences.sort(key=lambda x: x[1])
        return similar_experiences[0][0]

    def get_recommended_crop(self, image_width: int, image_height: int, display_scale: float = 1.0) -> Optional[Tuple[int, int, int, int]]:
        """
        获取推荐裁剪区域（基于纵横比和缩放后水平位置比例）

        Args:
            image_width: 图片宽度
            image_height: 图片高度
            display_scale: 显示缩放比例

        Returns:
            推荐裁剪区域 (x, y, width, height) 或 None
        """
        if image_width <= 0 or image_height <= 0:
            return None

        aspect_ratio = image_width / image_height

        # 查找相似经验
        similar_exp = self.find_similar_experience(aspect_ratio)

        if similar_exp is None:
            return None

        # 使用存储的水平位置比例（缩放后）
        x_position_ratio = similar_exp.x_position_ratio

        # 计算缩放后的图片长度
        scaled_image_width = image_width * display_scale

        # 计算裁剪框尺寸（等高模式）
        crop_height = image_height  # 裁剪框与图片等高
        standard_ratio = 870 / 1230
        crop_width = int(crop_height * standard_ratio)

        # 确保裁剪框宽度不超过图片宽度
        crop_width = min(crop_width, image_width)

        # 计算左上角顶点位置（在缩放后的图片长度上乘以百分比）
        new_x = int(x_position_ratio * scaled_image_width / display_scale)
        new_y = 0  # 始终从顶部开始

        # 确保不超出边界
        new_x = max(0, min(new_x, image_width - crop_width))

        return (new_x, new_y, crop_width, crop_height)

    def get_experience_count(self) -> int:
        """获取经验数量"""
        return len(self.experiences)

    def clear_memory(self):
        """清空所有裁剪经验"""
        self.experiences = []
        self.save_memory()
        print("裁剪记忆已清空")
