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
import time
import uuid
import xml.etree.ElementTree as ET
import zipfile
from typing import Any, Dict, List, Optional, Tuple

import config
from parsers.file_parser import (generate_smart_title,
                                 parse_volume_from_filename)
from processors.utils import file_tag, thread_tag
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
                print(f"{thread_tag()}   📋 字段 [{key}] {status}: 已有=[{str(old_val)[:60]}]  新=[{str(new_val)[:60]}]")
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
        print(f"{thread_tag()} ⚠️  检查ZIP文件失败 [{zip_path}]: {str(e)[:50]}")
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
        print(f"{thread_tag()} ⚠️  读取ZIP文件XML失败 [{zip_path}]: {str(e)[:50]}")
        return None


def resolve_save_target(zip_path: str, save_format: Optional[str] = None,
                        delete_after_convert: Optional[bool] = None) -> Tuple[Optional[str], bool]:
    """按保存格式设置解析输出目标（供 add_file_to_zip 使用）

    Args:
        zip_path: 源文件路径
        save_format: 保存格式（keep/cbz/zip/cb7），默认读 config.SAVE_FORMAT
        delete_after_convert: 转换成功后是否删除原文件，默认读 config.DELETE_AFTER_CONVERT

    Returns:
        (target_ext, keep_original)：
        - target_ext=None 表示保持原格式（zip/cbz 原地写，无需转换）
        - target_ext='.cbz'/'.zip'/'.cb7' 表示强制转换到该扩展名
        - keep_original=True 时转换后保留原文件；False 时转换成功后删除
    """
    if save_format is None:
        save_format = config.SAVE_FORMAT
    if delete_after_convert is None:
        delete_after_convert = config.DELETE_AFTER_CONVERT
    target_ext = config.SAVE_FORMAT_EXT.get(save_format)
    if target_ext is None:
        # 保持原格式：zip/cbz 原地写；rar/cbr/7z 无法原地写，自动转 CBZ 并固定保留原文件
        if zip_path.lower().endswith(('.cbr', '.rar', '.7z')):
            return '.cbz', True
        return None, True
    return target_ext, not delete_after_convert


def _fallback_write(zip_path: str, file_content: str, file_name: str,
                    target_exists: bool, target_ext: Optional[str],
                    keep_original: bool) -> bool:
    """7z 不可用/失败时的兜底写入：zip/cbz 用 zipfile，其它归档走通用转换

    Args:
        zip_path: 源归档文件路径
        file_content: 待写入的 XML 内容
        file_name: 文件名
        target_exists: 目标 XML 是否已存在（供 _add_with_zipfile 打印提示用）
        target_ext: 解析出的目标扩展名（None 表示保持原格式）
        keep_original: 转换成功后是否保留原文件

    Returns:
        bool: 是否成功
    """
    if zip_path.lower().endswith(('.cbz', '.zip')):
        # zip/cbz 本质是 zip，无需 7z 即可原地写
        return _add_with_zipfile(zip_path, file_content, file_name,
                                 xml_exists=bool(target_exists))
    return _handle_archive_format(zip_path, file_content, file_name,
                                  target_ext=target_ext or '.zip',
                                  keep_original=keep_original)


def add_file_to_zip(zip_path: str, file_content: str, file_name: str = 'ComicInfo.xml',
                    target_ext: Optional[str] = None,
                    prechecked: Optional[Tuple[bool, bool, List[str]]] = None) -> bool:
    """向 ZIP/CBZ/CBR/RAR/7Z 文件添加或更新文件

    保存格式由 config.SAVE_FORMAT 决定（keep/cbz/zip/cb7），也可通过
    target_ext 显式指定目标扩展名（None 时按设置解析）：
    - keep: zip/cbz 原地写；rar/cbr/7z 自动转 .cbz 并保留原文件
    - cbz/zip: 统一转 .cbz/.zip（zip 容器，zipfile 写）
    - cb7: 统一转 .cb7（7z 容器，7z.exe 写）
    格式转换成功后是否删除原文件由 config.DELETE_AFTER_CONVERT 决定
    （keep 模式 rar/cbr/7z 自动转换固定保留原文件）。

    Args:
        zip_path: 源归档文件路径
        file_content: 待写入的 XML 内容
        file_name: 文件名（默认 ComicInfo.xml）
        target_ext: 显式指定目标扩展名（'.cbz'/'.zip'/'.cb7'/None 按设置）
        prechecked: 调用方已 check 过的结果 (target_exists, content_matches,
            other_xml_files)；传入则跳过内部 check_zip_xml_files 二次检查，
            避免「字段删除」等差异日志重复打印。None 时保持原行为（自行检查）。

    Returns:
        bool: 是否成功
    """
    if target_ext is None:
        target_ext, keep_original = resolve_save_target(zip_path)
    else:
        keep_original = not config.DELETE_AFTER_CONVERT
    current_ext = os.path.splitext(zip_path)[1].lower()

    try:
        # 检查文件是否存在
        if not os.path.exists(zip_path):
            print(f"{thread_tag()} 🔴 文件不存在: {zip_path}")
            return False

        # 需要转换格式：手动选择 CBZ/ZIP/CB7，或 keep 模式下 rar/cbr/7z 自动转 CBZ
        if target_ext is not None and current_ext != target_ext:
            print(f"{thread_tag()} 🔄 检测到格式转换 {file_tag(zip_path)} → {target_ext}")
            if current_ext in ('.cbz', '.zip') and target_ext in ('.cbz', '.zip'):
                # zip 容器互转：zipfile 写，无需 7z
                return _convert_zip_container(zip_path, file_content, file_name,
                                              target_ext, keep_original)
            return _handle_archive_format(zip_path, file_content, file_name,
                                          target_ext=target_ext,
                                          keep_original=keep_original)

        # 目标扩展名与当前一致（或 keep 模式 zip/cbz）：原地写，保留扩展名
        # 检查文件中的XML文件情况：prechecked 已由调用方 check 过则直接复用，
        # 避免二次 check 导致「字段删除」等差异日志重复打印
        if prechecked is not None:
            target_exists, content_matches, other_xml_files = prechecked
        else:
            try:
                target_exists, content_matches, other_xml_files = check_zip_xml_files(zip_path, file_content, file_name)
            except Exception as e:
                print(f"{thread_tag()} ⚠️  检查文件失败 {file_tag(zip_path)}，可能是RAR格式: {str(e)[:50]}")
                # 假设文件是归档格式，需要特殊处理
                return _fallback_write(zip_path, file_content, file_name,
                                       target_exists=False,
                                       target_ext=target_ext,
                                       keep_original=keep_original)
        
        # 导入配置
        from config import MODE_SKIP_XMLEXIST

        # 模式1：有XML就跳过（不比较内容）
        if MODE_SKIP_XMLEXIST == 1 and target_exists:
            print(f"{thread_tag()} ⏭️  跳过已有XML的文件 {file_tag(zip_path)}: {file_name}")
            return True  # 有XML就跳过，不处理
        
        # 模式2：只处理已有XML的文件（修正模式）
        if MODE_SKIP_XMLEXIST == 2 and not target_exists:
            print(f"{thread_tag()} ⏭️  跳过没有XML的文件 {file_tag(zip_path)}: {file_name}")
            return True  # 没有XML就跳过，只处理有XML的文件
        
        # 模式0：按现有策略修改（默认）
        # 1. 如果有其它名称的XML文件（包括临时文件），必须删除并用新的ComicInfo.xml复写
        if other_xml_files:
            # 过滤出需要删除的临时文件
            temp_files = [f for f in other_xml_files if f.startswith('.temp_')]
            # 过滤出其它非临时XML文件
            other_xml_files = [f for f in other_xml_files if not f.startswith('.temp_')]
            
            if temp_files:
                print(f"{thread_tag()} ⚠️  发现临时文件 {file_tag(zip_path)}: {temp_files}，需要删除")
            if other_xml_files:
                print(f"{thread_tag()} ⚠️  发现其它XML文件 {file_tag(zip_path)}: {other_xml_files}，强制删除并用{file_name}复写")
            
            # 合并所有需要删除的文件
            files_to_delete = temp_files + other_xml_files
            
            # 继续执行后续的写入逻辑（包含删除其它XML文件）
        
        # 2. 如果没有其它XML文件，但有ComicInfo.xml，比较内容决定是否复写
        elif target_exists and content_matches:
            print(f"{thread_tag()} ⏭️  XML内容一致，跳过文件 {file_tag(zip_path)}: {file_name}")
            return True  # 内容一致，无需处理
        
        # 3. 其它情况（目标文件不存在，或内容不一致）都需要处理
        # 继续执行后续的写入逻辑
        
        files_to_delete = locals().get('files_to_delete', [])

        # zip/cbz 原地写：统一走 zipfile 流式重写（ZIP_STORED），不再 7z a -si
        # （7z -si 更新 DEFLATE 原卷需解压+重压整个 154-269MB 大卷，慢 + 文件占用
        #   重试最终把原卷替换成只含 XML 的空壳丢图，故 zip/cbz 直接走 zipfile）
        if current_ext in ('.zip', '.cbz'):
            return _add_with_zipfile(zip_path, file_content, file_name,
                                     xml_exists=bool(target_exists),
                                     files_to_delete=files_to_delete)

        # 非 zip 容器（.cb7 等）保留 7z 原地写路径
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
                        print(f"{thread_tag()} ✅ 使用7-Zip成功删除文件 {file_tag(zip_path)}: {xml_file}")
                    else:
                        print(f"{thread_tag()} ⚠️  删除文件失败 {file_tag(zip_path)}: {xml_file}")
            
            # 使用7-Zip的stdin功能直接从临时文件添加，避免在目标文件夹创建文件
            # 这样可以减少对目标硬盘的读写操作
            # 7z.exe 退出有延迟可能短暂占用 zip 文件，失败后递增等待重试即可恢复
            MAX_RETRIES = 3
            result = None
            for attempt in range(1, MAX_RETRIES + 1):
                if os.name == 'nt':  # Windows系统
                    # 使用7-Zip的-si参数从stdin读取数据
                    # 每次尝试都要重新打开文件（stdin读取会消耗文件指针，不能复用同一句柄）
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
                    break
                if attempt < MAX_RETRIES:
                    print(f"{thread_tag()} ⚠️  7-Zip命令执行失败 {file_tag(zip_path)}，第{attempt}次重试: {result.stderr.strip()}")
                    time.sleep(0.5 * attempt)  # 递增等待，让 7z.exe 释放句柄

            if result.returncode == 0:
                if target_exists or other_xml_files:
                    print(f"{thread_tag()} ✅ 使用7-Zip成功更新文件 {file_tag(zip_path)}: {file_name}")
                else:
                    print(f"{thread_tag()} ✅ 使用7-Zip成功添加文件 {file_tag(zip_path)}: {file_name}")
                return True
            else:
                print(f"{thread_tag()} ⚠️  7-Zip命令执行失败(重试{MAX_RETRIES}次) {file_tag(zip_path)}: {result.stderr.strip()}")
                # 尝试通用归档格式处理
                print(f"{thread_tag()} 🔄 尝试通用归档格式处理...")
                return _fallback_write(zip_path, file_content, file_name,
                                       target_exists=bool(target_exists),
                                       target_ext=target_ext,
                                       keep_original=keep_original)
        else:
            # 7-Zip不可用，尝试通用归档格式处理
            print(f"{thread_tag()} ⚠️  7-Zip未找到，尝试通用归档格式处理")
            return _fallback_write(zip_path, file_content, file_name,
                                   target_exists=bool(target_exists),
                                   target_ext=target_ext,
                                   keep_original=keep_original)
            
    except Exception as e:
        print(f"{thread_tag()} 🔴 添加文件失败 [{zip_path}]: {str(e)[:50]}")
        # 尝试通用归档格式处理
        print(f"{thread_tag()} 🔄 尝试通用归档格式处理...")
        try:
            return _fallback_write(zip_path, file_content, file_name,
                                   target_exists=locals().get('target_exists', False),
                                   target_ext=target_ext,
                                   keep_original=keep_original)
        except Exception:
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
        print(f"{thread_tag()} ⚠️  检查归档文件失败 [{archive_path}]: {str(e)[:50]}")
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
        print(f"{thread_tag()} ⚠️  读取归档文件XML失败 [{archive_path}]: {str(e)[:50]}")
        return None

from .seven_zip_handler import (_add_with_zipfile, _check_seven_zip_available,
                                _convert_zip_container, _extract_file_via_seven_zip,
                                _handle_archive_format, _list_xml_files_via_seven_zip,
                                _run_seven_zip)

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

