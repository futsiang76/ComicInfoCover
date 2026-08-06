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

def _check_seven_zip_available() -> str:
    """检查7-Zip是否可用，并返回其路径
    
    Returns:
        str: 7-Zip可执行文件的路径，如果不可用返回空字符串
    """
    try:
        # 首先尝试直接运行7z.exe（如果在PATH中）
        result = subprocess.run(
            ['cmd', '/c', '7z.exe', '--help'],
            capture_output=True,
            text=True
        )
        if result.returncode == 0 or "7-Zip" in result.stdout:
            return "7z.exe"
        
        # 尝试7za.exe（命令行版本）
        result = subprocess.run(
            ['cmd', '/c', '7za.exe', '--help'],
            capture_output=True,
            text=True
        )
        if result.returncode == 0 or "7-Zip" in result.stdout:
            return "7za.exe"
        
        # 检查常见的安装路径
        common_paths = [
            r"C:\Program Files\7-Zip\7z.exe",
            r"C:\Program Files (x86)\7-Zip\7z.exe",
            r"D:\Program Files\7-Zip\7z.exe",
            r"D:\Program Files (x86)\7-Zip\7z.exe"
        ]
        
        for path in common_paths:
            if os.path.exists(path):
                return path
        
        return ""
    except (subprocess.SubprocessError, FileNotFoundError):
        return ""

def _add_with_zipfile(zip_path: str, file_content: str, file_name: str, xml_exists: bool = False) -> bool:
    """使用zipfile模块的回退方法
    
    Args:
        zip_path: ZIP文件路径
        file_content: 文件内容
        file_name: 文件名
        xml_exists: XML文件是否已存在
    """
    import shutil
    import zipfile
    
    try:
        # 明确在本地PC的临时目录创建ZIP临时文件
        temp_dir = tempfile.gettempdir()  # 获取系统临时目录
        temp_zip_path = os.path.join(temp_dir, f"temp_{os.path.basename(zip_path)}")
        
        # 复制原始zip文件到临时文件
        shutil.copy2(zip_path, temp_zip_path)
        
        # 读取原始文件内容
        with zipfile.ZipFile(temp_zip_path, 'r') as zf:
            # 读取所有文件（除了要更新的文件）
            file_contents = {}
            for name in zf.namelist():
                if name != file_name:
                    try:
                        file_contents[name] = zf.read(name)
                    except Exception as e:
                        print(f"⚠️  读取文件失败 [{name}]: {str(e)[:30]}")
        
        # 写入所有文件到临时zip
        with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_STORED, allowZip64=True) as zf:
            # 写入所有原始文件
            for name, content in file_contents.items():
                zf.writestr(name, content)
            # 写入新文件
            zf.writestr(file_name, file_content.encode('utf-8'))
        
        # CRC校验：验证临时ZIP文件完整性
        try:
            with zipfile.ZipFile(temp_zip_path, 'r') as zf:
                bad_file = zf.testzip()
                if bad_file is None:
                    print("   🔍 CRC校验通过: 临时ZIP文件完整")
                else:
                    print(f"   ⚠️  CRC校验失败: 损坏的文件 {bad_file}")
                    raise Exception(f"临时ZIP文件CRC校验失败: {bad_file}")
        except Exception as e:
            print(f"   ⚠️  CRC校验异常: {str(e)}")
            raise Exception(f"临时ZIP文件CRC校验异常: {str(e)}")
        
        # 只有CRC校验通过，才复制回原文件
        shutil.copy2(temp_zip_path, zip_path)
        
        if xml_exists:
            print(f"✅ 使用zipfile成功更新文件: {file_name}")
        else:
            print(f"✅ 使用zipfile成功添加文件: {file_name}")
        
        # 删除临时文件
        if os.path.exists(temp_zip_path):
            os.unlink(temp_zip_path)
        
        return True
    except Exception as e:
        print(f"🔴 回退方法失败: {str(e)[:50]}")
        return False

def _handle_archive_format(zip_path: str, file_content: str, file_name: str = 'ComicInfo.xml') -> bool:
    """处理RAR、CBR、CBZ格式文件，并用ZIP复写回去
    
    Args:
        zip_path: 文件路径
        file_content: 文件内容
        file_name: 文件名
        
    Returns:
        bool: 是否成功
    """
    import re
    import shutil
    
    try:
        # 检查7-Zip是否可用
        seven_zip_path = _check_seven_zip_available()
        if not seven_zip_path:
            print("🔴 7-Zip不可用，无法处理归档格式")
            return False
        
        # 创建临时目录（为每个实例生成唯一路径）
        temp_dir = tempfile.gettempdir()
        # 使用安全的目录名，避免特殊字符，并添加唯一标识符
        safe_basename = re.sub(r'[<>"|?*]', '_', os.path.basename(zip_path))
        instance_id = str(uuid.uuid4())[:8]  # 生成8位唯一标识符
        extract_dir = os.path.join(temp_dir, f"extract_{instance_id}_{safe_basename}")
        os.makedirs(extract_dir, exist_ok=True)
        
        # 提取文件内容
        print(f"🔄 提取文件内容...")
        extract_success = False
        
        # 尝试不同的提取方法（只保留成功的方法）
        extraction_methods = [
            # 方法1: 自动识别格式（不带引号）
            lambda: _run_seven_zip(seven_zip_path, ['x', '-y', zip_path, f'-o{extract_dir}'])
        ]
        
        for i, method in enumerate(extraction_methods):
            try:
                print(f"   尝试提取方法 {i+1}...")
                result = method()
                if result.returncode == 0:
                    print("   ✅ 提取成功")
                    extract_success = True
                    break
                else:
                    # 不显示具体错误信息，直接显示下一步
                    print("   ⚠️  提取失败，尝试下一步处理")
            except Exception as e:
                print("   ⚠️  方法执行失败，尝试下一步处理")
        
        if not extract_success:
            print("🔴 所有提取方法都失败")
            return False
        
        # 写入新的XML文件
        xml_path = os.path.join(extract_dir, file_name)
        with open(xml_path, 'w', encoding='utf-8') as xml_file:
            xml_file.write(file_content)
        
        # 创建临时ZIP文件（为每个实例生成唯一路径）
        # 使用唯一标识符避免多实例冲突
        safe_temp_name = f"temp_{instance_id}_{re.sub(r'[\\s]', '_', safe_basename)}.zip"
        temp_zip_path = os.path.join(temp_dir, safe_temp_name)
        
        # 将提取的内容重新压缩为ZIP
        print(f"🔄 重新压缩为ZIP格式...")
        zip_success = False
                
        # 尝试不同的压缩方法（只保留成功的方法）
        compression_methods = [
            # 方法1: 正常压缩（不带引号）
            lambda: _run_seven_zip(seven_zip_path, ['a', '-tzip', '-mm=copy', '-y', temp_zip_path, f'{extract_dir}/*'])
        ]
        
        for i, method in enumerate(compression_methods):
            try:
                print(f"   尝试压缩方法 {i+1}...")
                result = method()
                if result.returncode == 0:
                    print("   ✅ 压缩成功")
                    zip_success = True
                    break
                else:
                    # 不显示具体错误信息，直接显示下一步
                    print("   ⚠️  压缩失败，尝试下一步处理")
            except Exception as e:
                print("   ⚠️  方法执行失败，尝试下一步处理")
        
        if not zip_success:
            print("🔴 所有压缩方法都失败")
            return False
        
        # 替换原始文件，并将扩展名改为.zip
        # 生成新的文件名（将.cbr/.cbz/.rar改为.zip）
        base_name = os.path.splitext(zip_path)[0]  # 去掉原扩展名
        new_zip_path = base_name + '.zip'
        
        # 复制临时ZIP文件到新位置
        shutil.copy2(temp_zip_path, new_zip_path)
        
        # 删除原始文件（可选，根据需求决定）
        if zip_path != new_zip_path:  # 确保不是同一个文件
            try:
                os.remove(zip_path)
                print(f"🗑️  已删除原始文件: {os.path.basename(zip_path)}")
            except Exception as e:
                print(f"⚠️  删除原始文件失败: {str(e)}")
        
        print(f"✅ 成功将文件转换为ZIP并添加文件: {file_name}")
        print(f"📁 新文件: {os.path.basename(new_zip_path)}")
        
        # 清理临时文件
        if os.path.exists(extract_dir):
            shutil.rmtree(extract_dir)
        if os.path.exists(temp_zip_path):
            os.unlink(temp_zip_path)
        
        return True
    except Exception as e:
        print(f"🔴 处理归档格式失败: {str(e)[:50]}")
        # 清理临时文件
        if 'extract_dir' in locals() and os.path.exists(extract_dir):
            try:
                shutil.rmtree(extract_dir)
            except:
                pass
        if 'temp_zip_path' in locals() and os.path.exists(temp_zip_path):
            try:
                os.unlink(temp_zip_path)
            except:
                pass
        return False

def _run_seven_zip(seven_zip_path: str, args: list) -> subprocess.CompletedProcess:
    """运行7-Zip命令
    
    Args:
        seven_zip_path: 7-Zip可执行文件路径
        args: 命令参数列表
        
    Returns:
        subprocess.CompletedProcess: 命令执行结果
    """
    if os.name == 'nt':  # Windows系统
        # 直接调用7-Zip，不使用cmd
        cmd_list = [seven_zip_path] + args
        # 不显示具体命令，避免显示错误信息
        return subprocess.run(
            cmd_list,
            capture_output=True,
            text=True,
            shell=True  # 使用shell=True确保路径正确处理
        )
    else:  # Unix-like系统
        cmd_list = [seven_zip_path] + args
        return subprocess.run(
            cmd_list,
            capture_output=True,
            text=True
        )

