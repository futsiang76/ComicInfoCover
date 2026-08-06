#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
处理器共享工具函数 - 无循环依赖风险
"""

import os
from typing import Dict, List, Optional, Tuple


def process_short_story_folder(folder_path: str, folder_info: Dict, depth: int = 0) -> Dict:
    """处理短篇文件夹
    
    Args:
        folder_path: 文件夹路径
        folder_info: 文件夹信息
        depth: 当前深度
        
    Returns:
        Dict: 处理结果
    """
    print(f"{'  ' * depth}📋 检测到短篇内容，跳过Bangumi查询")
    
    # 创建XML模板处理器
    template_handler = create_xml_template_handler()
    comic_info_base = template_handler.create_base_template(folder_info, is_short_story=True)
    
    # 设置模拟结果
    selected_result = {"id": 0, "name": folder_info["series"], "name_cn": folder_info["series"]}
    
    return {
        "comic_info_base": comic_info_base,
        "selected_result": selected_result,
        "skip_files": False
    }




def process_xml_modify_folder(folder_path: str, folder_info: Dict, depth: int = 0) -> Dict:
    """从XML文件中读取元数据（修正模式）
    
    Args:
        folder_path: 文件夹路径
        folder_info: 文件夹信息
        depth: 当前深度
        
    Returns:
        Dict: 处理结果
    """
    print(f"{'  ' * depth}📖 从XML文件读取元数据")
    
    from processors.zip_handler import read_xml_from_zip
    from processors.xml_template_handler import create_xml_template_handler
    
    # 尝试从文件夹中的第一个ZIP文件读取XML
    comic_info_base = None
    xml_source_file = None
    
    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        if not os.path.isfile(file_path):
            continue
        if not filename.lower().endswith(('.zip', '.cbz', '.cbr', '.rar')):
            continue
        
        # 尝试读取XML
        xml_data = read_xml_from_zip(file_path)
        if xml_data:
            comic_info_base = xml_data
            xml_source_file = filename
            print(f"{'  ' * depth}  ✅ 从 {filename} 读取到XML数据")
            break
    
    if not comic_info_base:
        print(f"{'  ' * depth}❌ 未找到有效的XML文件，使用本地信息")
        # 如果没有找到XML，使用本地信息
        template_handler = create_xml_template_handler()
        comic_info_base = template_handler.create_local_template(folder_info)
    
    # 设置模拟结果
    selected_result = {
        "id": comic_info_base.get("Web", "").split("/")[-1] if comic_info_base.get("Web") else "",
        "name": comic_info_base.get("Series", folder_info["series"]),
        "name_cn": comic_info_base.get("Series", folder_info["series"])
    }
    
    return {
        "comic_info_base": comic_info_base,
        "selected_result": selected_result,
        "skip_files": False,
        "xml_source_file": xml_source_file
    }




def check_all_files_have_xml(folder_path: str) -> bool:
    """检查文件夹下所有ZIP文件是否都已包含XML文件
    
    Args:
        folder_path: 文件夹路径
        
    Returns:
        bool: 是否所有文件都已包含XML
    """
    import zipfile
    
    try:
        # 获取文件夹下所有ZIP文件
        zip_files = [f for f in os.listdir(folder_path) 
                    if f.endswith('.zip') or f.endswith('.cbz') or f.endswith('.cbr') or f.endswith('.rar')]
        
        if not zip_files:
            return False  # 没有ZIP文件，需要处理
        
        # 检查每个ZIP文件是否包含ComicInfo.xml
        for zip_file in zip_files:
            zip_path = os.path.join(folder_path, zip_file)
            
            try:
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    file_list = zf.namelist()
                    
                    # 检查是否有ComicInfo.xml文件
                    if 'ComicInfo.xml' not in file_list:
                        return False  # 至少有一个文件没有XML
            except Exception:
                # 如果无法打开ZIP文件，假设需要处理
                return False
        
        # 所有文件都包含XML
        return True
        
    except Exception as e:
        print(f"⚠️  检查文件夹XML状态失败: {str(e)[:50]}")
        return False  # 出错时假设需要处理


        # 统计结果
    print("\n" + "="*80)
    print("📊 批量处理完成 - 统计结果")
    print(f"📁 总文件夹数: {total_folders}")
    print(f"✅ 自动处理: {auto_processed} | 手动处理: {manual_processed} | 跳过: {skipped}")
    print(f"📄 文件统计: 总计{total_files}个 | 成功{success_files}个")
    print(f"💡 成功率: {success_files/total_files*100:.1f}%" if total_files > 0 else "💡 无文件处理")
    print("="*80)


