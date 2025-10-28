#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
IPTV直播源终极整理工具

工作流程：
1. 优先加载local.txt → 补充网络源 → 合并去重
2. 严格按demo.txt模板过滤（非模板频道全部丢弃）
3. 全频道FFmpeg测速（每个频道独立进度条）
4. 每个频道保留最优8个有效源
5. 生成带响应时间的iptv.txt和iptv.m3u
"""

import requests
import re
import os
import subprocess
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

MAX_SOURCES = 8           # 每个频道保留最优源数
SPEED_TEST_TIMEOUT = 5     # 测速超时(秒)
MAX_WORKERS = 6            # 并发测速线程数

# ====================== 核心引擎 ======================
class IPTVProcessor:
    def __init__(self):
        self.template_channels = set()
        self.blacklist = self.load_blacklist()
        self.load_template()

    def load_blacklist(self):
        """加载黑名单域名关键词"""
        if os.path.exists(BLACKLIST_FILE):
            with open(BLACKLIST_FILE, 'r', encoding='utf-8') as f:
                return [line.strip().lower() for line in f if line.strip()]
        return []

    def load_template(self):
        """加载模板并构建频道集合"""
        if os.path.exists(TEMPLATE_FILE):
            with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.endswith(",#genre#"):
                        self.template_channels.add(self.clean_name(line))

    def clean_name(self, name):
        """深度清洗频道名称"""
        name = re.sub(r'CCTV[\s\-_]?(\d+)', lambda m: f"CCTV-{m.group(1)}", name, flags=re.IGNORECASE)
        name = re.sub(r'[·|_（）【】]', '', name)
        return name.strip()

    def fetch_sources(self):
        """获取所有源（本地优先）"""
        sources = []
        
        # 优先加载本地源
        if os.path.exists(LOCAL_SOURCE):
            with open(LOCAL_SOURCE, 'r', encoding='utf-8') as f:
                print(f"✅ 已加载本地源: {LOCAL_SOURCE}")
                sources.append(f.read())

        # 补充网络源
        print("🌐 抓取网络源...")
        with tqdm(URLS, desc="进度") as pbar:
            for url in pbar:
                if self.is_blocked(url):
                    pbar.write(f"🚫 跳过黑名单URL: {url}")
                    continue
                
                if content := self.fetch_url(url):
                    sources.append(content)
                else:
                    pbar.write(f"⚠️ 获取失败: {url.split('/')[-1]}")
        
        return "\n".join(sources)

    def fetch_url(self, url):
        """抓取单个URL内容"""
        try:
            r = requests.get(url, timeout=10)
            r.encoding = 'utf-8'
            return r.text if r.status_code == 200 else None
        except:
            return None

    def is_blocked(self, url):
        """检查URL是否在黑名单中"""
        domain = urlparse(url).netloc.split(':')[0].lower()
        return any(kw in domain for kw in self.blacklist)

    def parse_sources(self, content):
        """解析所有源并过滤非模板频道"""
        channels = defaultdict(list)
        
        # 判断内容格式
        is_m3u = content.startswith("#EXTM3U")
        
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
                
            if is_m3u and line.startswith("#EXTINF"):
                # 处理M3U格式
                if match := re.search(r'tvg-name="([^"]+)"', line):
                    name = self.clean_name(match.group(1))
                    if name in self.template_channels:
                        current_name = name
            elif not is_m3u and ',' in line:
                # 处理TXT格式
                name, url = line.split(',', 1)
                name = self.clean_name(name.strip())
                if name in self.template_channels:
                    channels[name].append(url.strip())
            elif line.startswith("http") and current_name:
                # M3U的URL行
                channels[current_name].append(line.strip())
                current_name = None
        
        return channels

    def speed_test(self, url):
        """增强版测速函数"""
        try:
            start = time.time()
            cmd = [
                "ffmpeg", "-i", url,
                "-t", str(SPEED_TEST_TIMEOUT),
                "-f", "null", "-",
                "-v", "quiet", "-stats"
            ]
            subprocess.run(cmd, check=True, 
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE,
                         timeout=SPEED_TEST_TIMEOUT)
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
        """处理所有频道（测速+筛选）"""
        result = []
        total_channels = len(channels)
        
        with tqdm(total=total_channels, desc="🔄 频道处理进度") as chan_pbar:
            for name, urls in channels.items():
                chan_pbar.set_postfix_str(f"{name[:10]}...")
                
                # 测速当前频道的所有源
                speed_results = []
                with tqdm(urls, desc=f"⏱️ {name[:15]}", leave=False) as url_pbar:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                        futures = [executor.submit(self.speed_test, url) for url in urls]
                        for future in concurrent.futures.as_completed(futures):
                            speed_results.append(future.result())
                            url_pbar.update(1)
                
                # 筛选最优源
                valid_sources = [s for s in speed_results if s['status'] == 'success']
                valid_sources.sort(key=lambda x: x['time'])
                best_sources = valid_sources[:MAX_SOURCES]
                
                result.append({
                    "name": name,
                    "sources": best_sources,
                    "best_time": best_sources[0]['time'] if best_sources else None
                })
                chan_pbar.update(1)
        
        return sorted(result, key=lambda x: x['best_time'] or float('inf'))

    def generate_output(self, channels):
        """生成输出文件"""
        # 加载模板结构
        with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
            template = [line.strip() for line in f if line.strip()]
        
        # 生成TXT
        with open(OUTPUT_TXT, 'w', encoding='utf-8') as f:
            current_genre = ""
            for line in template:
                if line.endswith(",#genre#"):
                    current_genre = line.replace(",#genre#", "")
                    f.write(f"\n{current_genre},#genre#\n")
                else:
                    name = self.clean_name(line)
                    if name in (c['name'] for c in channels):
                        channel = next(c for c in channels if c['name'] == name)
                        for src in channel['sources']:
                            f.write(f"{name},{src['url']} #响应:{int(src['time'])}ms\n")
        
        # 生成M3U
        with open(OUTPUT_M3U, 'w', encoding='utf-8') as f:
            f.write("#EXTM3U\n")
            current_genre = ""
            for line in template:
                if line.endswith(",#genre#"):
                    current_genre = line.replace(",#genre#", "")
                else:
                    name = self.clean_name(line)
                    if name in (c['name'] for c in channels):
                        channel = next(c for c in channels if c['name'] == name)
                        for src in channel['sources']:
                            f.write(f'#EXTINF:-1 tvg-name="{name}" group-title="{current_genre}",{name}\n{src["url"]}\n')

# ====================== 主程序 ======================
if __name__ == "__main__":
    print("🎬 IPTV直播源终极整理工具")
    print(f"🛠️ 配置: 超时{SPEED_TEST_TIMEOUT}s | 保留{MAX_SOURCES}源 | 并发{MAX_WORKERS}线程")
    
    processor = IPTVProcessor()
    
    print("\n🔍 正在获取直播源...")
    content = processor.fetch_sources()
    
    print("\n🧹 正在清洗数据...")
    channels = processor.parse_sources(content)
    print(f"📊 有效频道: {len(channels)} | 待测速源: {sum(len(u) for u in channels.values())}")
    
    print("\n⚡ 正在全频道测速...")
    processed_channels = processor.process_channels(channels)
    
    print("\n💾 正在生成输出文件...")
    processor.generate_output(processed_channels)
    
    print(f"\n🎉 处理完成！生成文件: {OUTPUT_TXT} 和 {OUTPUT_M3U}")
