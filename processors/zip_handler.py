#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZIP处理器模块 - 高效处理ZIP/CBZ文件

使用7-Zip命令行工具提高性能，支持秒级处理大文件
"""

import os
import re
import shutil
import subprocess
import tempfile
import uuid
import xml.etree.ElementTree as ET
import zipfile
from typing import Any, Dict, List, Optional, Tuple

from parsers.file_parser import (generate_smart_title,
                                 parse_volume_from_filename)
from processors.xml_generator import XMLGenerator

from .zip_operations import (add_file_to_zip, check_zip_xml_files, get_zip_info,
                              read_xml_from_zip, _check_seven_zip_available,
                              _compare_xml_content, _handle_archive_format,
                              check_zip_integrity, _add_with_zipfile)

class FileHandler:
    """文件处理器类"""
    
    def __init__(self):
        """初始化文件处理器"""
        self.xml_generator = XMLGenerator()
    
    def process_comic_files(self, folder_path: str, comic_info_base: Dict[str, Any], 
                           folder_info: Dict[str, Any], skip_files: bool = False, 
                           manga_value: Optional[str] = None) -> Tuple[int, int]:
        """处理文件夹中的漫画文件
        
        Args:
            folder_path: 文件夹路径
            comic_info_base: 基础ComicInfo数据
            folder_info: 文件夹信息
            skip_files: 是否跳过文件处理
            manga_value: Manga字段值（"Yes"或"No"），为None时使用input询问
            
        Returns:
            Tuple[int, int]: (总文件数, 成功文件数)
        """
        total_files = 0
        success_files = 0
        
        if skip_files:
            print("⚠️  跳过文件处理")
            return total_files, success_files
        
        # 判断是否为Manga
        if manga_value is None:
            manga_input = input("是否为Manga？(Y/n): ").strip().lower()
            manga_value = "No" if manga_input == "n" else "Yes"
        comic_info_base["Manga"] = manga_value
        print(f"📖 Manga字段设置为: {comic_info_base['Manga']}")
        
        try:
            for file in os.listdir(folder_path):
                file_path = os.path.join(folder_path, file)
                
                if not os.path.isfile(file_path):
                    continue
                
                if not file.lower().endswith(('.zip', '.cbz', '.cbr', '.rar', '.7z')):
                    continue
                
                total_files += 1
                
                # 为每个文件生成特定的XML
                xml_content = self.xml_generator.generate_for_file(
                    comic_info_base, file, folder_info
                )
                
                # 写入XML到ZIP文件
                result = add_file_to_zip(file_path, xml_content)
                
                if result is True:
                    success_files += 1
                    # 在add_file_to_zip中已经打印了成功信息
                elif result is False:
                    print(f"❌ 写入失败: {file}")
                else:
                    # 跳过的情况（内容一致）
                    print(f"⏭️  跳过文件（内容一致）: {file}")
                    success_files += 1  # 跳过也算成功处理
        
        except Exception as e:
            print(f"🔴 处理文件失败: {str(e)[:50]}")
        
        return total_files, success_files
    
    def scan_comic_files(self, folder_path: str) -> List[str]:
        """扫描文件夹中的漫画文件
        
        Args:
            folder_path: 文件夹路径
            
        Returns:
            List[str]: 漫画文件列表
        """
        comic_files = []
        
        try:
            for file in os.listdir(folder_path):
                file_path = os.path.join(folder_path, file)
                
                if not os.path.isfile(file_path):
                    continue
                
                if file.lower().endswith(('.zip', '.cbz', '.cbr', '.rar', '.7z')):
                    comic_files.append(file)
        
        except Exception as e:
            print(f"🔴 扫描文件失败: {str(e)[:50]}")
        
        return comic_files
    
    def validate_comic_file(self, file_path: str) -> Dict[str, Any]:
        """验证漫画文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            Dict[str, Any]: 验证结果
        """
        result = {
            'valid': False,
            'is_zip': False,
            'exists': False,
            'integrity': False,
            'size': 0,
            'error': ''
        }
        
        try:
            result['exists'] = os.path.exists(file_path)
            if not result['exists']:
                result['error'] = '文件不存在'
                return result
            
            result['is_zip'] = file_path.lower().endswith(('.zip', '.cbz', '.cbr', '.rar', '.7z'))
            if not result['is_zip']:
                result['error'] = '不是ZIP/CBZ文件'
                return result
            
            result['size'] = os.path.getsize(file_path)
            result['integrity'] = check_zip_integrity(file_path)
            result['valid'] = result['integrity']
            
            if not result['integrity']:
                result['error'] = 'ZIP文件损坏'
        
        except Exception as e:
            result['error'] = str(e)[:50]
        
        return result


def create_file_handler() -> FileHandler:
    """创建文件处理器实例
    
    Returns:
        FileHandler: 文件处理器实例
    """
    return FileHandler()
