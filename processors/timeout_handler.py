#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
超时处理器模块 - 统一管理所有超时相关的逻辑
"""

import time
import threading
from typing import Optional, List, Dict, Any, Callable
from config import WAITING_TIME


class TimeoutHandler:
    """超时处理器类"""
    
    def __init__(self, default_timeout: Optional[int] = None):
        """初始化超时处理器
        
        Args:
            default_timeout: 默认超时时间（秒），None表示使用全局配置
        """
        self.default_timeout = default_timeout or WAITING_TIME
    
    def get_timeout_value(self, timeout: Optional[int] = None) -> int:
        """获取实际的超时时间值
        
        Args:
            timeout: 指定的超时时间
            
        Returns:
            int: 实际的超时时间值
        """
        if timeout is None:
            return self.default_timeout
        return timeout
    
    def is_infinite_wait(self, timeout: Optional[int] = None) -> bool:
        """检查是否为无限等待模式
        
        Args:
            timeout: 超时时间
            
        Returns:
            bool: 是否为无限等待
        """
        timeout_value = self.get_timeout_value(timeout)
        return timeout_value == 0
    
    def get_user_input(self, prompt: str, timeout: Optional[int] = None) -> Optional[str]:
        """获取用户输入，支持超时
        
        Args:
            prompt: 提示信息
            timeout: 超时时间（秒），None表示使用默认配置
            
        Returns:
            Optional[str]: 用户输入或None（超时）
        """
        timeout_value = self.get_timeout_value(timeout)
        
        if self.is_infinite_wait(timeout_value):
            # 无限等待模式
            return input(prompt)
        
        # 超时处理
        from typing import List, Optional
        result: List[Optional[str]] = [None]

        def get_input():
            try:
                result[0] = input(prompt)
            except:
                result[0] = None
        
        input_thread = threading.Thread(target=get_input)
        input_thread.daemon = True
        input_thread.start()
        input_thread.join(timeout_value)
        
        if input_thread.is_alive():
            print("⏰ 等待超时")
            return None
        
        return result[0]
    
    def get_user_choice(self, prompt: str, valid_choices: List[str], 
                       timeout: Optional[int] = None) -> Optional[str]:
        """获取用户选择，支持超时和输入验证
        
        Args:
            prompt: 提示信息
            valid_choices: 有效选择列表
            timeout: 超时时间（秒），None表示使用默认配置
            
        Returns:
            Optional[str]: 用户选择或None（超时/无效输入）
        """
        timeout_value = self.get_timeout_value(timeout)
        
        if self.is_infinite_wait(timeout_value):
            # 无限等待模式
            while True:
                choice = input(prompt).strip()
                if choice in valid_choices:
                    return choice
                else:
                    print("❌ 输入无效，请重新输入")
        
        # 超时处理
        start_time = time.time()
        while True:
            # 检查是否超时
            if timeout_value > 0 and time.time() - start_time > timeout_value:
                print("⏰ 等待超时")
                return None
            
            choice = self.get_user_input(prompt, timeout_value)
            if choice is None:
                return None
            
            if choice in valid_choices:
                return choice
            else:
                print("❌ 输入无效，请重新输入")
    
    def execute_with_timeout(self, func: Callable, timeout: Optional[int] = None, 
                           *args, **kwargs) -> Any:
        """在指定超时时间内执行函数
        
        Args:
            func: 要执行的函数
            timeout: 超时时间（秒）
            *args: 函数参数
            **kwargs: 函数关键字参数
            
        Returns:
            Any: 函数执行结果，超时返回None
        """
        timeout_value = self.get_timeout_value(timeout)
        
        if self.is_infinite_wait(timeout_value):
            # 无限等待模式
            return func(*args, **kwargs)
        
        # 超时处理
        from typing import List, Optional, Any, Union
        result: List[Optional[Any]] = [None]
        exception: List[Optional[Exception]] = [None]
        
        def execute_func():
            try:
                result[0] = func(*args, **kwargs)
            except Exception as e:
                exception[0] = e
        
        thread = threading.Thread(target=execute_func)
        thread.daemon = True
        thread.start()
        thread.join(timeout_value)
        
        if thread.is_alive():
            print("⏰ 操作超时")
            return None
        
        if exception[0] is not None:
            raise exception[0]
        
        return result[0]
    
    def wait_with_timeout(self, condition_func: Callable[[], bool], 
                         timeout: Optional[int] = None, 
                         check_interval: float = 0.1) -> bool:
        """等待条件满足，支持超时
        
        Args:
            condition_func: 条件检查函数
            timeout: 超时时间（秒）
            check_interval: 检查间隔（秒）
            
        Returns:
            bool: 条件是否在超时前满足
        """
        timeout_value = self.get_timeout_value(timeout)
        
        if self.is_infinite_wait(timeout_value):
            # 无限等待模式
            while not condition_func():
                time.sleep(check_interval)
            return True
        
        # 超时处理
        start_time = time.time()
        while True:
            if condition_func():
                return True
            
            if time.time() - start_time > timeout_value:
                print("⏰ 等待超时")
                return False
            
            time.sleep(check_interval)
    
    def handle_timeout_fallback(self, fallback_func: Callable, 
                              timeout: Optional[int] = None,
                              *args, **kwargs) -> Any:
        """处理超时回退逻辑
        
        Args:
            fallback_func: 超时时执行的备用函数
            timeout: 超时时间（秒）
            *args: 备用函数参数
            **kwargs: 备用函数关键字参数
            
        Returns:
            Any: 主操作结果或备用函数结果
        """
        def main_operation():
            # 这里可以放置需要超时保护的主操作
            # 例如等待用户输入
            return self.get_user_input("请输入: ", timeout)
        
        result = self.execute_with_timeout(main_operation, timeout)
        
        if result is None:
            # 超时，执行备用函数
            print("⏰ 操作超时，执行备用方案")
            return fallback_func(*args, **kwargs)
        
        return result
    
    def format_timeout_message(self, timeout: Optional[int] = None) -> str:
        """格式化超时提示消息
        
        Args:
            timeout: 超时时间（秒）
            
        Returns:
            str: 格式化后的超时消息
        """
        timeout_value = self.get_timeout_value(timeout)
        
        if self.is_infinite_wait(timeout_value):
            return "无限等待模式"
        
        return f"⏰ 等待时间: {timeout_value}秒，超时将自动处理..."
    
    def create_timeout_context(self, timeout: Optional[int] = None, 
                             context_name: str = "操作") -> Dict[str, Any]:
        """创建超时上下文信息
        
        Args:
            timeout: 超时时间（秒）
            context_name: 上下文名称
            
        Returns:
            Dict[str, Any]: 超时上下文信息
        """
        timeout_value = self.get_timeout_value(timeout)
        
        return {
            "timeout": timeout_value,
            "is_infinite": self.is_infinite_wait(timeout_value),
            "message": self.format_timeout_message(timeout_value),
            "context_name": context_name,
            "start_time": time.time()
        }
    
    def check_timeout_remaining(self, context: Dict[str, Any]) -> float:
        """检查剩余超时时间
        
        Args:
            context: 超时上下文
            
        Returns:
            float: 剩余时间（秒），负数表示已超时
        """
        if context["is_infinite"]:
            return float('inf')
        
        elapsed = time.time() - context["start_time"]
        remaining = context["timeout"] - elapsed
        return max(0, remaining)


def create_timeout_handler(default_timeout: Optional[int] = None) -> TimeoutHandler:
    """创建超时处理器实例
    
    Args:
        default_timeout: 默认超时时间（秒）
        
    Returns:
        TimeoutHandler: 超时处理器实例
    """
    return TimeoutHandler(default_timeout)