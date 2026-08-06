#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图像裁剪模块（P3 裁剪用）— 逻辑拷贝自 007 image_handler/image_cropper.py（只读引用）

裁剪基于 PIL，crop_region 为原图坐标 (x, y, width, height)。
标准裁剪尺寸继承 007 config 默认值（870x1230）。
"""
from pathlib import Path
from typing import Tuple

from PIL import Image

from processors.cover_utils import STANDARD_HEIGHT, STANDARD_WIDTH


class ImageCropper:
    """按指定区域裁剪图片并保存（与 007 行为一致）"""

    def crop_image(self, source_path: Path, target_path: Path,
                   crop_region: Tuple[int, int, int, int]) -> bool:
        """裁剪图片并保存

        Args:
            source_path: 源图片路径
            target_path: 目标图片路径
            crop_region: 裁剪区域 (x, y, width, height)

        Returns:
            bool: 裁剪是否成功
        """
        try:
            with Image.open(source_path) as img:
                x, y, width, height = crop_region
                img_width, img_height = img.size

                # 裁剪区域夹紧到图片范围内
                x = max(0, min(x, img_width - 1))
                y = max(0, min(y, img_height - 1))
                width = min(width, img_width - x)
                height = min(height, img_height - y)

                if width <= 0 or height <= 0:
                    return False

                cropped_img = img.crop((x, y, x + width, y + height))
                cropped_img.save(target_path, quality=95)
                return True
        except Exception as e:
            print(f"⚠️   裁剪图片失败: {e}")
            return False

    def calculate_crop_region(self, img_width: int, img_height: int,
                              target_width: int, target_height: int) -> Tuple[int, int, int, int]:
        """计算居中裁剪区域（覆盖式缩放后取中心）

        Returns:
            Tuple[起始x, 起始y, 裁剪宽度, 裁剪高度]
        """
        width_ratio = target_width / img_width
        height_ratio = target_height / img_height
        scale = max(width_ratio, height_ratio)
        crop_width = int(target_width / scale)
        crop_height = int(target_height / scale)
        x = (img_width - crop_width) // 2
        y = (img_height - crop_height) // 2
        return x, y, crop_width, crop_height

    def get_standard_crop_size(self) -> Tuple[int, int]:
        """获取标准裁剪尺寸"""
        return STANDARD_WIDTH, STANDARD_HEIGHT
