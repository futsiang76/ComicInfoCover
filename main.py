#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
漫画元数据处理主程序

功能：
1. 批量解析漫画文件夹 → 按作品名搜索Bangumi
2. 支持别名搜索：主标题搜索失败时自动尝试括号内的别名
3. 智能卷数提取：从每个zip/cbz文件名中提取卷数信息
4. 多作者匹配：支持[marginal×竹谷州史]格式的多作者匹配
5. 扩展作者类型：匹配作者、作画、原作、脚本、监督等多种类型
6. 总卷数识别：正确解析V03全、短篇等格式，写入XML总卷数字段
7. 特殊文件处理：C45单话文件、设定集等额外内容特殊处理
8. 匹配失败时列出前10个结果，手动选择后处理
9. 生成ComicInfo.xml并写入zip/cbz（卷数来自文件名）
10. 支持指定Bangumi ID处理单个系列文件夹，不规则文件夹下按单卷系列处理
"""

import sys

from processors.single_series_processor import create_single_series_processor


def select_modes():
    """选择运行模式"""
    # 导入配置模块
    import config
    
    print("🔧 请选择运行模式：")
    print("  0. 全匹配模式 - 按现有全匹配策略修改ZIP文件")
    print("  1. 补漏模式 - 跳过已有XML的文件夹，只处理没有XML的新文件夹")
    print("  2. 修正模式 - 只处理已有XML的文件")
    print("  3. 手动匹配模式 - 人工到 Bangumi 查询编号，输入 Bangumi ID 后扫描")
    
    while True:
        try:
            mode = input("请输入模式编号 (0-3，默认0): ").strip()
            if mode == "":
                mode_skip_xml = 0
                break
            elif mode in ["0", "1", "2", "3"]:
                mode_skip_xml = int(mode)
                break
            else:
                print("❌ 输入无效，请输入 0、1、2 或 3")
        except ValueError:
            print("❌ 输入无效，请输入数字")
    
    # 如果是手动匹配模式（模式3），直接返回，不再询问无人值守模式
    if mode_skip_xml == 3:
        print(f"\n⚙️  当前配置：")
        print(f"   操作模式: 手动匹配模式")
        print(f"   MODE_SKIP_XMLEXIST = {mode_skip_xml}")
        print(f"   AUTO_TURBO_MATCH = {config.AUTO_TURBO_MATCH}")
        
        # 更新配置文件中的值
        config.MODE_SKIP_XMLEXIST = mode_skip_xml
        return mode_skip_xml  # 返回模式值3，让main函数正确处理
    
    print("\n🤖 请选择是否开启无人值守模式：")
    print("  0. 关闭 - 需要手动选择匹配结果")
    print("  1. 开启 - 唯一匹配自动处理，其他情况跳过")
    
    while True:
        try:
            mode = input("请输入模式编号 (0-1，默认0): ").strip()
            if mode == "":
                auto_turbo = 0
                break
            elif mode in ["0", "1"]:
                auto_turbo = int(mode)
                break
            else:
                print("❌ 输入无效，请输入 0 或 1")
        except ValueError:
            print("❌ 输入无效，请输入数字")
    
    print(f"\n⚙️  当前配置：")
    print(f"   MODE_SKIP_XMLEXIST = {mode_skip_xml}")
    print(f"   AUTO_TURBO_MATCH = {auto_turbo}")
    
    # 更新配置文件中的值
    config.MODE_SKIP_XMLEXIST = mode_skip_xml
    config.AUTO_TURBO_MATCH = auto_turbo
    
    return mode_skip_xml

def main():
    """主函数"""
    try:
        # 选择运行模式
        mode_skip_xml = select_modes()
        
        # 检查是否是模式3（手动匹配模式）
        if mode_skip_xml == 3:
            # 模式3：手动匹配模式
            from processors.single_series_processor import \
                create_single_series_processor
            processor = create_single_series_processor()
            processor.run_interactive()
            return
        
        # 获取路径
        from utils.path_helper import get_manga_root_path
        manga_root = get_manga_root_path()
        
        print(f"\n🚀 开始处理漫画目录: {manga_root}")
        print("="*80)
        
        # 开始处理
        from processors.folder_processors import batch_process
        batch_process(manga_root)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断操作，处理终止")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n🔴 程序异常终止: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()