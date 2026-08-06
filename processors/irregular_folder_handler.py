#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
不规范文件夹处理器模块 - 处理不规范文件夹中的每个ZIP文件

对于不规范文件夹，每个ZIP文件都会独立处理：
1. 从文件名提取作者和系列信息
2. 尝试从Bangumi搜索匹配
3. 生成XML并写入ZIP文件
"""

import os
from typing import Dict, List, Optional, Tuple

from models.bangumi_fetcher import BangumiFetcher
from parsers.file_parser import parse_filename_info


def process_irregular_folder(folder_path: str, fetcher: BangumiFetcher, depth: int = 0) -> Dict:
    """处理不规范文件夹（每个ZIP文件独立匹配）
    
    Args:
        folder_path: 文件夹路径
        fetcher: Bangumi获取器
        depth: 当前深度
        
    Returns:
        Dict: 处理结果
    """
    print(f"{'  ' * depth}📋 检测到不规范文件夹，每个ZIP文件独立处理")
    
    # 标记为需要特殊处理
    return {
        "comic_info_base": None,
        "selected_result": "irregular",
        "skip_files": False
    }


def process_irregular_folder_files(folder_path: str, fetcher: BangumiFetcher, depth: int = 0, manga_value: Optional[str] = None) -> Tuple[int, int]:
    """处理不规范文件夹中的文件（每个文件独立匹配）
    
    Args:
        folder_path: 文件夹路径
        fetcher: Bangumi获取器
        depth: 当前深度
        manga_value: Manga字段值（"Yes"或"No"），为None时使用input询问
        
    Returns:
        Tuple[int, int]: (总文件数, 成功文件数)
    """
    # 导入需要的模块
    import zipfile

    from config import AUTO_TURBO_MATCH, MODE_SKIP_XMLEXIST
    from processors.scan_processors import process_normal_folder
    from processors.xml_generator import XMLGenerator
    from processors.zip_handler import add_file_to_zip
    
    total_files = 0
    success_files = 0
    
    # 判断是否为Manga
    if manga_value is None:
        manga_input = input("是否为Manga？(Y/n): ").strip().lower()
        manga_value = "No" if manga_input == "n" else "Yes"
    print(f"📖 Manga字段设置为: {manga_value}")
    
    try:
        # 创建XML生成器
        xml_generator = XMLGenerator()
        
        for file in os.listdir(folder_path):
            file_path = os.path.join(folder_path, file)
            
            if not os.path.isfile(file_path):
                continue
            
            if not file.lower().endswith(('.zip', '.cbz', '.cbr', '.rar')):
                continue
            
            total_files += 1
            
            # 检查文件是否需要跳过
            file_path = os.path.join(folder_path, file)
            if MODE_SKIP_XMLEXIST == 1:
                # 高速模式：跳过已有XML的文件
                try:
                    with zipfile.ZipFile(file_path, 'r') as zf:
                        if 'ComicInfo.xml' in zf.namelist():
                            print(f"{'  ' * (depth + 1)}⏭️  高速模式：文件已有XML，跳过: {file}")
                            continue
                except Exception:
                    # 如果无法打开ZIP文件，继续处理
                    pass
            elif MODE_SKIP_XMLEXIST == 2:
                # 修正模式：只处理已有XML的文件
                try:
                    with zipfile.ZipFile(file_path, 'r') as zf:
                        if 'ComicInfo.xml' not in zf.namelist():
                            print(f"{'  ' * (depth + 1)}⏭️  修正模式：文件无XML，跳过: {file}")
                            continue
                except Exception:
                    # 如果无法打开ZIP文件，跳过
                    print(f"{'  ' * (depth + 1)}⏭️  修正模式：无法打开文件，跳过: {file}")
                    continue
            
            print("="*80)
            print(f"{'  ' * (depth + 1)}📦 处理文件: {file}")
            
            # 从文件名提取信息
            file_info = parse_filename_info(file)
            if not file_info:
                print(f"{'  ' * (depth + 1)}❌ 无法解析文件名: {file}")
                print("="*80)
                continue
            
            # 打印提取的信息
            print(f"{'  ' * (depth + 1)}✍️ 作者: {file_info.get('author', '未知')}")
            print(f"{'  ' * (depth + 1)}📖 标题: {file_info.get('series', '未知')}")
            print("="*80)
            
            # 构建文件夹信息
            file_folder_info = {
                "author": file_info.get('author', '未知'),
                "series": file_info.get('series', '未知'),
                "vol_info": file_info.get('vol_info', 'V01'),
                "total_volumes": file_info.get('total_volumes', 1),
                "complete": file_info.get('complete', True),
                "vol_type": file_info.get('vol_type', '短篇'),
                "tags": file_info.get('tags', [])
            }
            
            # 复用现有的搜索逻辑
            result = process_normal_folder(folder_path, file_folder_info, fetcher, depth + 1)
            
            if result.get("skip_files"):
                print(f"{'  ' * (depth + 2)}⏭️  跳过文件")
            else:
                # 检查是否有有效的comic_info_base
                if not result.get("comic_info_base"):
                    print(f"{'  ' * (depth + 2)}❌ 无有效信息，跳过文件")
                    continue
                
                # 获取comic_info_base（创建深拷贝避免多实例冲突）
                import copy
                comic_info_base = copy.deepcopy(result["comic_info_base"])
                
                # 设置Manga字段
                comic_info_base["Manga"] = manga_value
                
                # 添加标签信息到comic_info_base
                tags = file_info.get('tags', [])
                if tags:
                    if 'Tags' in comic_info_base:
                        # 合并现有标签
                        existing_tags = comic_info_base['Tags'].split(',') if comic_info_base['Tags'] else []
                        new_tags = existing_tags + tags
                        # 去重
                        unique_tags = list(dict.fromkeys(new_tags))
                        comic_info_base['Tags'] = ','.join(unique_tags)
                    else:
                        # 添加新标签
                        comic_info_base['Tags'] = ','.join(tags)
                    print(f"{'  ' * (depth + 2)}🏷️  添加标签: {', '.join(tags)}")
                
                # 为当前文件生成XML
                xml_content = xml_generator.generate_for_file(
                    comic_info_base, file, file_folder_info
                )
                
                # 写入XML到ZIP文件
                write_result = add_file_to_zip(file_path, xml_content)
                
                if write_result is True:
                    success_files += 1
                elif write_result is False:
                    print(f"{'  ' * (depth + 2)}❌ 写入失败: {file}")
                else:
                    # 跳过的情况
                    print(f"{'  ' * (depth + 2)}⏭️  跳过文件: {file}")
                
                # 添加分割线
                print("="*80)
    
    except Exception as e:
        print(f"{'  ' * depth}🔴 处理不规范文件夹失败: {str(e)[:50]}")
    
    return total_files, success_files


def is_irregular_folder(folder_info: Dict) -> bool:
    """判断是否是不规范文件夹
    
    Args:
        folder_info: 文件夹信息
        
    Returns:
        bool: 是否是不规范文件夹
    """
    return folder_info.get('from_filename', False)