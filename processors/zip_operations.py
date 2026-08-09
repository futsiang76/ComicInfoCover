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

def _compare_xml_content(existing_xml: str, new_xml: str) -> bool:
    """比较两个XML内容是否语义一致（忽略字段顺序、空白差异和空字段）

    所有非空字段的变化（新增/删除/修改）均视为不一致。
    只有字段全集相同且每个字段值相同时才视为一致。

    Args:
        existing_xml: 已有的XML内容
        new_xml: 新的XML内容

    Returns:
        bool: 内容是否一致
    """
    try:
        existing_root = ET.fromstring(existing_xml)
        new_root = ET.fromstring(new_xml)

        existing_fields = {}
        for child in existing_root:
            text = (child.text or "").strip()
            if text:
                existing_fields[child.tag] = text

        new_fields = {}
        for child in new_root:
            text = (child.text or "").strip()
            if text:
                new_fields[child.tag] = text

        # 双向检测：任何字段变化（新增/删除/修改）均为不一致
        all_keys = set(existing_fields.keys()) | set(new_fields.keys())
        for key in sorted(all_keys):
            old_val = existing_fields.get(key, "")
            new_val = new_fields.get(key, "")
            if old_val != new_val:
                status = "删除" if not new_val else "新增" if not old_val else "修改"
                print(f"  📋 字段 [{key}] {status}: 已有=[{str(old_val)[:60]}]  新=[{str(new_val)[:60]}]")
                return False

        return True
    except ET.ParseError:
        existing_clean = re.sub(r'\s+', ' ', existing_xml.strip())
        new_clean = re.sub(r'\s+', ' ', new_xml.strip())
        return existing_clean == new_clean


def check_zip_xml_files(zip_path: str, new_xml_content: str, target_file_name: str = 'ComicInfo.xml') -> Tuple[bool, bool, List[str]]:
    """检查ZIP文件中的XML文件情况
    
    Args:
        zip_path: ZIP文件路径
        new_xml_content: 新的XML内容
        target_file_name: 目标XML文件名
        
    Returns:
        Tuple[bool, bool, List[str]]: (目标文件是否存在, 内容是否一致, 其它XML文件列表)
    """
    try:
        # 检查ZIP文件是否存在
        if not os.path.exists(zip_path):
            return False, False, []
        
        # cbr/rar/7z 归档走 7-Zip 检查（zipfile 无法直接打开）
        if zip_path.lower().endswith(('.cbr', '.rar', '.7z')):
            return _check_xml_via_seven_zip(zip_path, new_xml_content, target_file_name)
        
        # 使用zipfile检查文件
        with zipfile.ZipFile(zip_path, 'r') as zf:
            file_list = zf.namelist()
            
            # 查找所有XML文件
            xml_files = [f for f in file_list if f.lower().endswith('.xml')]
            
            # 查找其它名称的XML文件（非目标文件，包括临时文件）
            other_xml_files = [f for f in xml_files if f != target_file_name]
            
            # 检查目标XML文件是否存在
            target_exists = target_file_name in file_list
            
            # 如果目标文件存在，比较内容
            content_matches = False
            if target_exists:
                existing_content = zf.read(target_file_name).decode('utf-8')
                content_matches = _compare_xml_content(existing_content, new_xml_content)
            
            return target_exists, content_matches, other_xml_files
            
    except Exception as e:
        print(f"⚠️  检查ZIP文件失败 [{zip_path}]: {str(e)[:50]}")
        return False, False, []


def read_xml_from_zip(zip_path: str, target_file_name: str = 'ComicInfo.xml') -> Optional[Dict]:
    """从ZIP文件中读取ComicInfo.xml内容
    
    Args:
        zip_path: ZIP文件路径
        target_file_name: 目标XML文件名
        
    Returns:
        Optional[Dict]: XML内容字典，失败返回None
    """
    try:
        # 检查ZIP文件是否存在
        if not os.path.exists(zip_path):
            return None
        
        # cbr/rar/7z 归档走 7-Zip 读取（zipfile 无法直接打开）
        if zip_path.lower().endswith(('.cbr', '.rar', '.7z')):
            return _read_xml_via_seven_zip(zip_path, target_file_name)
        
        # 使用zipfile读取文件
        with zipfile.ZipFile(zip_path, 'r') as zf:
            file_list = zf.namelist()
            
            # 检查目标XML文件是否存在
            if target_file_name not in file_list:
                return None
            
            # 读取XML内容
            xml_content = zf.read(target_file_name).decode('utf-8')
            
            # 解析XML
            root = ET.fromstring(xml_content)
            
            # 提取所有字段
            comic_info = {}
            for child in root:
                comic_info[child.tag] = (child.text or "").strip()
            
            return comic_info
            
    except Exception as e:
        print(f"⚠️  读取ZIP文件XML失败 [{zip_path}]: {str(e)[:50]}")
        return None


def add_file_to_zip(zip_path: str, file_content: str, file_name: str = 'ComicInfo.xml') -> bool:
    """向ZIP/CBZ/CBR/RAR文件添加或更新文件"""
    try:
        # 检查文件是否存在
        if not os.path.exists(zip_path):
            print(f"🔴 文件不存在: {zip_path}")
            return False
        
        # 如果是.cbr/.rar/.7z文件，直接走格式转换逻辑（cbz=zip 走下方 zipfile/7z 更新，保留扩展名）
        if zip_path.lower().endswith(('.cbr', '.rar', '.7z')):
            print(f"🔄 检测到归档格式文件，进行格式转换: {os.path.basename(zip_path)}")
            return _handle_archive_format(zip_path, file_content, file_name)
        
        # 尝试检查文件中的XML文件情况
        try:
            target_exists, content_matches, other_xml_files = check_zip_xml_files(zip_path, file_content, file_name)
        except Exception as e:
            print(f"⚠️  检查文件失败，可能是RAR格式: {str(e)[:50]}")
            # 假设文件是归档格式，需要特殊处理
            return _handle_archive_format(zip_path, file_content, file_name)
        
        # 导入配置
        from config import MODE_SKIP_XMLEXIST

        # 模式1：有XML就跳过（不比较内容）
        if MODE_SKIP_XMLEXIST == 1 and target_exists:
            print(f"⏭️  跳过已有XML的文件: {file_name}")
            return True  # 有XML就跳过，不处理
        
        # 模式2：只处理已有XML的文件（修正模式）
        if MODE_SKIP_XMLEXIST == 2 and not target_exists:
            print(f"⏭️  跳过没有XML的文件: {file_name}")
            return True  # 没有XML就跳过，只处理有XML的文件
        
        # 模式0：按现有策略修改（默认）
        # 1. 如果有其它名称的XML文件（包括临时文件），必须删除并用新的ComicInfo.xml复写
        if other_xml_files:
            # 过滤出需要删除的临时文件
            temp_files = [f for f in other_xml_files if f.startswith('.temp_')]
            # 过滤出其它非临时XML文件
            other_xml_files = [f for f in other_xml_files if not f.startswith('.temp_')]
            
            if temp_files:
                print(f"⚠️  发现临时文件: {temp_files}，需要删除")
            if other_xml_files:
                print(f"⚠️  发现其它XML文件: {other_xml_files}，强制删除并用{file_name}复写")
            
            # 合并所有需要删除的文件
            files_to_delete = temp_files + other_xml_files
            
            # 继续执行后续的写入逻辑（包含删除其它XML文件）
        
        # 2. 如果没有其它XML文件，但有ComicInfo.xml，比较内容决定是否复写
        elif target_exists and content_matches:
            print(f"⏭️  XML内容一致，跳过文件: {file_name}")
            return True  # 内容一致，无需处理
        
        # 3. 其它情况（目标文件不存在，或内容不一致）都需要处理
        # 继续执行后续的写入逻辑
        
        # 明确在本地PC的临时目录创建临时文件，减少目标硬盘的读取
        temp_dir = tempfile.gettempdir()  # 获取系统临时目录
        instance_id = str(uuid.uuid4())[:8]  # 生成8位唯一标识符
        temp_file_path = os.path.join(temp_dir, f"temp_{instance_id}_{file_name}")
        
        # 写入文件内容
        with open(temp_file_path, 'w', encoding='utf-8') as temp_file:
            temp_file.write(file_content)
        
        # 检查7-Zip是否可用
        seven_zip_path = _check_seven_zip_available()
        
        if seven_zip_path:
            # 如果有需要删除的文件，先删除它们
            if 'files_to_delete' in locals() and files_to_delete:
                # 使用7-Zip删除其它XML文件
                for xml_file in files_to_delete:
                    if os.name == 'nt':  # Windows系统
                        delete_result = subprocess.run(
                            ['cmd', '/c', seven_zip_path, 'd', '-y', zip_path, xml_file],
                            capture_output=True,
                            text=True,
                            encoding='utf-8',
                            errors='replace'
                        )
                    else:  # Unix-like系统
                        delete_result = subprocess.run(
                            [seven_zip_path, 'd', '-y', zip_path, xml_file],
                            capture_output=True,
                            text=True
                        )
                    
                    if delete_result.returncode == 0:
                        print(f"✅ 使用7-Zip成功删除文件: {xml_file}")
                    else:
                        print(f"⚠️  删除文件失败: {xml_file}")
            
            # 使用7-Zip的stdin功能直接从临时文件添加，避免在目标文件夹创建文件
            # 这样可以减少对目标硬盘的读写操作
            if os.name == 'nt':  # Windows系统
                # 使用7-Zip的-si参数从stdin读取数据
                with open(temp_file_path, 'rb') as xml_file:
                    result = subprocess.run(
                        ['cmd', '/c', seven_zip_path, 'a', '-mm=copy', '-y', '-si' + file_name, zip_path],
                        stdin=xml_file,
                        capture_output=True,
                        text=True,
                        encoding='utf-8',
                        errors='replace'
                    )
            else:  # Unix-like系统
                # 对于Unix系统，使用类似的方法
                with open(temp_file_path, 'rb') as xml_file:
                    result = subprocess.run(
                        [seven_zip_path, 'a', '-mm=copy', '-y', '-si' + file_name, zip_path],
                        stdin=xml_file,
                        capture_output=True,
                        text=True,
                        encoding='utf-8',
                        errors='replace'
                    )
            
            if result.returncode == 0:
                if target_exists or other_xml_files:
                    print(f"✅ 使用7-Zip成功更新文件: {file_name}")
                else:
                    print(f"✅ 使用7-Zip成功添加文件: {file_name}")
                return True
            else:
                print(f"⚠️  7-Zip命令执行失败: {result.stderr.strip()}")
                # 尝试通用归档格式处理
                print("🔄 尝试通用归档格式处理...")
                return _handle_archive_format(zip_path, file_content, file_name)
        else:
            # 7-Zip不可用，尝试通用归档格式处理
            print("⚠️  7-Zip未找到，尝试通用归档格式处理")
            return _handle_archive_format(zip_path, file_content, file_name)
            
    except Exception as e:
        print(f"🔴 添加文件失败 [{zip_path}]: {str(e)[:50]}")
        # 尝试通用归档格式处理
        print("🔄 尝试通用归档格式处理...")
        try:
            return _handle_archive_format(zip_path, file_content, file_name)
        except:
            return False
    finally:
        # 清理临时文件
        if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except:
                pass

def _check_xml_via_seven_zip(archive_path: str, new_xml_content: str,
                             target_file_name: str = 'ComicInfo.xml') -> Tuple[bool, bool, List[str]]:
    """用7-Zip检查cbr/rar/7z归档中的XML文件情况

    Args:
        archive_path: 归档文件路径
        new_xml_content: 新的XML内容
        target_file_name: 目标XML文件名

    Returns:
        Tuple[bool, bool, List[str]]: (目标文件是否存在, 内容是否一致, 其它XML文件列表)
    """
    try:
        xml_files = _list_xml_files_via_seven_zip(archive_path)

        # 查找其它名称的XML文件（非目标文件，包括临时文件）
        other_xml_files = [f for f in xml_files if os.path.basename(f) != target_file_name]

        # 检查目标XML文件是否存在
        target_exists = any(os.path.basename(f) == target_file_name for f in xml_files)

        # 如果目标文件存在，比较内容
        content_matches = False
        if target_exists:
            existing_content = _extract_file_via_seven_zip(archive_path, target_file_name)
            if existing_content is not None:
                content_matches = _compare_xml_content(existing_content, new_xml_content)

        return target_exists, content_matches, other_xml_files
    except Exception as e:
        print(f"⚠️  检查归档文件失败 [{archive_path}]: {str(e)[:50]}")
        return False, False, []


def _read_xml_via_seven_zip(archive_path: str,
                            target_file_name: str = 'ComicInfo.xml') -> Optional[Dict]:
    """用7-Zip从cbr/rar/7z归档中读取ComicInfo.xml内容

    Args:
        archive_path: 归档文件路径
        target_file_name: 目标XML文件名

    Returns:
        Optional[Dict]: XML内容字典，失败返回None
    """
    try:
        xml_content = _extract_file_via_seven_zip(archive_path, target_file_name)
        if xml_content is None:
            return None

        # 解析XML
        root = ET.fromstring(xml_content)

        # 提取所有字段
        comic_info = {}
        for child in root:
            comic_info[child.tag] = (child.text or "").strip()

        return comic_info
    except Exception as e:
        print(f"⚠️  读取归档文件XML失败 [{archive_path}]: {str(e)[:50]}")
        return None

from .seven_zip_handler import (_add_with_zipfile, _check_seven_zip_available,
                                _extract_file_via_seven_zip, _handle_archive_format,
                                _list_xml_files_via_seven_zip, _run_seven_zip)

def check_zip_integrity(zip_path: str) -> bool:
    """检查ZIP/CBZ/CBR/RAR文件完整性"""
    try:
        # 使用7-Zip检查文件完整性
        seven_zip_path = _check_seven_zip_available()
        if seven_zip_path:
            result = subprocess.run(
                ['cmd', '/c', seven_zip_path, 't', zip_path],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            return result.returncode == 0
        else:
            # 回退到zipfile方法（仅适用于ZIP/CBZ）
            import zipfile
            try:
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    zf.testzip()
                return True
            except:
                # 可能是RAR/CBR格式，7-Zip不可用时无法检查
                return False
    except Exception:
        return False

def get_zip_info(zip_path: str) -> dict:
    """获取ZIP文件信息"""
    try:
        info = {
            'path': zip_path,
            'size': os.path.getsize(zip_path),
            'exists': os.path.exists(zip_path),
            'is_zip': zip_path.lower().endswith(('.zip', '.cbz', '.cbr', '.rar', '.7z'))
        }
        
        if info['is_zip'] and info['exists']:
            info['integrity'] = check_zip_integrity(zip_path)
        else:
            info['integrity'] = False
        
        return info
    except Exception as e:
        print(f"🔴 获取ZIP信息失败: {str(e)[:50]}")
        return {
            'path': zip_path,
            'exists': False,
            'is_zip': False,
            'integrity': False
        }

