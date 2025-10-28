#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
IPTV直播源整理工具
"""

import requests
import re
import os
import subprocess
import sys
from urllib.parse import urlparse
from collections import defaultdict
import concurrent.futures
import time
from tqdm import tqdm

# ====================== 配置区域 ======================
URLS = [
    "https://raw.githubusercontent.com/Supprise0901/TVBox_live/main/live.txt",
    "https://raw.githubusercontent.com/wwb521/live/main/tv.m3u", 
    "https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/ipv4/result.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/cn.m3u"
]

LOCAL_SOURCE = "local.txt"
BLACKLIST_FILE = "blacklist.txt"
TEMPLATE_FILE = "demo.txt"
OUTPUT_TXT = "iptv.txt"
OUTPUT_M3U = "iptv.m3u"

MAX_SOURCES = 8
SPEED_TEST_TIMEOUT = 5
MAX_WORKERS = 6

# ====================== 核心引擎 ======================
class IPTVProcessor:
    def __init__(self):
        self.template_channels = set()
        self.blacklist = self.load_blacklist()
        self.load_template()

    def load_blacklist(self):
        """加载黑名单"""
        blacklist = []
        if os.path.exists(BLACKLIST_FILE):
            try:
                with open(BLACKLIST_FILE, 'r', encoding='utf-8') as f:
                    blacklist = [line.strip().lower() for line in f if line.strip() and not line.startswith('#')]
            except:
                pass
        return blacklist

    def load_template(self):
        """加载模板频道"""
        if os.path.exists(TEMPLATE_FILE):
            with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.endswith(",#genre#"):
                        cleaned = self.clean_name(line)
                        if cleaned:
                            self.template_channels.add(cleaned)

    def clean_name(self, name):
        """清洗频道名称"""
        if not name:
            return ""
        name = re.sub(r'CCTV[\s\-_]?(\d+)', lambda m: f"CCTV-{m.group(1)}", name, flags=re.IGNORECASE)
        name = re.sub(r'[·|_（）【】\s]+', ' ', name)
        return name.strip()

    def fetch_sources(self):
        """获取直播源"""
        sources = []
        
        # 本地源
        if os.path.exists(LOCAL_SOURCE):
            with open(LOCAL_SOURCE, 'r', encoding='utf-8') as f:
                sources.append(f.read())
        
        # 网络源
        if URLS:
            for url in URLS:
                if not self.is_blocked(url):
                    if content := self.fetch_url(url):
                        sources.append(content)
        
        return "\n".join(sources)

    def fetch_url(self, url):
        """获取URL内容"""
        try:
            response = requests.get(url, timeout=10)
            return response.text if response.status_code == 200 else None
        except:
            return None

    def is_blocked(self, url):
        """检查黑名单"""
        try:
            domain = urlparse(url).netloc.lower()
            return any(kw in domain for kw in self.blacklist)
        except:
            return False

    def parse_sources(self, content):
        """修复版M3U/TXT解析器"""
        if not content:
            return defaultdict(list)
            
        channels = defaultdict(list)
        is_m3u = content.strip().startswith("#EXTM3U")
        current_name = None  # 关键修复：提前初始化
        
        print(f"解析{'M3U' if is_m3u else 'TXT'}格式数据...")
        
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
                
            try:
                if is_m3u:
                    # M3U格式处理 - 完全重写解析逻辑
                    if line.startswith("#EXTINF"):
                        # 从EXTINF行提取频道名
                        name = self.extract_name_from_extinf(line)
                        if name and name in self.template_channels:
                            current_name = name
                        else:
                            current_name = None
                    elif line.startswith("http") and current_name:
                        # 只有当前有有效频道名时才添加URL
                        channels[current_name].append(line)
                        current_name = None  # 重置当前频道名
                    elif line.startswith("http") and not current_name:
                        # 如果URL行前没有EXTINF，跳过这个无效条目
                        continue
                else:
                    # TXT格式处理
                    if ',' in line and not line.endswith(",#genre#"):
                        parts = line.split(',', 1)
                        if len(parts) == 2:
                            name, url = parts[0].strip(), parts[1].strip()
                            if url.startswith('http'):
                                name = self.clean_name(name)
                                if name in self.template_channels:
                                    channels[name].append(url)
            except Exception as e:
                # 跳过解析错误的行
                continue
        
        print(f"解析完成: {len(channels)}个频道")
        return channels

    def extract_name_from_extinf(self, extinf_line):
        """从EXTINF行提取频道名称"""
        try:
            # 方法1: 从tvg-name属性提取
            match = re.search(r'tvg-name="([^"]+)"', extinf_line)
            if match:
                return self.clean_name(match.group(1))
            
            # 方法2: 从逗号后的名称提取
            match = re.search(r',([^,]+)$', extinf_line)
            if match:
                return self.clean_name(match.group(1))
            
            # 方法3: 从group-title和名称组合提取
            match = re.search(r'group-title="[^"]*",(.+)$', extinf_line)
            if match:
                return self.clean_name(match.group(1))
                
        except:
            pass
        
        return None

    def speed_test(self, url):
        """测速函数"""
        try:
            start = time.time()
            subprocess.run([
                "ffmpeg", "-i", url, "-t", str(SPEED_TEST_TIMEOUT),
                "-f", "null", "-", "-v", "quiet", "-stats"
            ], check=True, timeout=SPEED_TEST_TIMEOUT, 
               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            return {
                "url": url,
                "time": (time.time() - start) * 1000,
                "status": "success"
            }
        except subprocess.TimeoutExpired:
            return {"url": url, "time": SPEED_TEST_TIMEOUT*1000, "status": "timeout"}
        except:
            return {"url": url, "time": float('inf'), "status": "error"}

    def process_channels(self, channels):
        """处理频道测速"""
        result = []
        
        for name, urls in channels.items():
            # 测速所有源
            speed_results = []
            for url in urls:
                speed_results.append(self.speed_test(url))
            
            # 筛选最优源
            valid_sources = [s for s in speed_results if s['status'] == 'success']
            valid_sources.sort(key=lambda x: x['time'])
            best_sources = valid_sources[:MAX_SOURCES]
            
            result.append({
                "name": name,
                "sources": best_sources,
                "best_time": best_sources[0]['time'] if best_sources else None
            })
        
        return result

    def generate_output(self, processed_channels):
        """生成输出文件"""
        # 读取模板结构
        template_lines = []
        if os.path.exists(TEMPLATE_FILE):
            with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
                template_lines = [line.strip() for line in f if line.strip()]
        
        # 生成TXT文件
        with open(OUTPUT_TXT, 'w', encoding='utf-8') as f:
            current_genre = "未分类"
            for line in template_lines:
                if line.endswith(",#genre#"):
                    current_genre = line.replace(",#genre#", "")
                    f.write(f"\n{current_genre},#genre#\n")
                else:
                    name = self.clean_name(line)
                    channel = next((c for c in processed_channels if c['name'] == name), None)
                    if channel and channel['sources']:
                        for source in channel['sources']:
                            time_info = f" #响应:{int(source['time'])}ms" if source['time'] < float('inf') else ""
                            f.write(f"{name},{source['url']}{time_info}\n")
        
        # 生成M3U文件
        with open(OUTPUT_M3U, 'w', encoding='utf-8') as f:
            f.write("#EXTM3U\n")
            current_genre = "未分类"
            for line in template_lines:
                if line.endswith(",#genre#"):
                    current_genre = line.replace(",#genre#", "")
                else:
                    name = self.clean_name(line)
                    channel = next((c for c in processed_channels if c['name'] == name), None)
                    if channel and channel['sources']:
                        for source in channel['sources']:
                            time_info = f" #响应:{int(source['time'])}ms" if source['time'] < float('inf') else ""
                            f.write(f'#EXTINF:-1 tvg-name="{name}" group-title="{current_genre}",{name}{time_info}\n{source["url"]}\n')

# ====================== 主程序 ======================
def main():
    print("IPTV直播源整理工具")
    
    processor = IPTVProcessor()
    
    # 获取源数据
    content = processor.fetch_sources()
    if not content:
        print("错误: 无法获取直播源数据")
        return
    
    # 解析数据
    channels = processor.parse_sources(content)
    if not channels:
        print("错误: 没有有效的频道数据")
        return
    
    # 测速处理
    processed_channels = processor.process_channels(channels)
    
    # 生成输出
    processor.generate_output(processed_channels)
    
    print("处理完成!")

if __name__ == "__main__":
    main()
