#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
IPTV直播源终极整理工具
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
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/cn.m3u",
    "https://raw.githubusercontent.com/suxuang/myIPTV/main/ipv4.m3u",
    "https://raw.githubusercontent.com/vbskycn/iptv/master/tv/iptv4.txt",
    "https://raw.githubusercontent.com/develop202/migu_video/refs/heads/main/interface.txt",
    "http://47.120.41.246:8899/zb.txt",
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
        self.success_count = 0
        self.failed_count = 0

    def load_blacklist(self):
        """加载黑名单域名关键词"""
        blacklist = []
        if os.path.exists(BLACKLIST_FILE):
            try:
                with open(BLACKLIST_FILE, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip().lower()
                        if line and not line.startswith('#'):
                            blacklist.append(line)
                print(f"✅ 已加载黑名单: {len(blacklist)}个关键词")
            except Exception as e:
                print(f"⚠️ 读取黑名单失败: {e}")
        return blacklist

    def load_template(self):
        """加载模板并构建频道集合"""
        if not os.path.exists(TEMPLATE_FILE):
            print(f"❌ 模板文件 {TEMPLATE_FILE} 不存在")
            return
            
        try:
            with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.endswith(",#genre#"):
                        cleaned_name = self.clean_name(line)
                        if cleaned_name:
                            self.template_channels.add(cleaned_name)
            print(f"✅ 已加载模板: {len(self.template_channels)}个频道")
        except Exception as e:
            print(f"❌ 读取模板失败: {e}")

    def clean_name(self, name):
        """深度清洗频道名称"""
        if not name:
            return ""
            
        try:
            # 标准化央视名称
            name = re.sub(r'CCTV[\s\-_]?(\d+)', lambda m: f"CCTV-{m.group(1)}", name, flags=re.IGNORECASE)
            name = re.sub(r'央视(\d+)', lambda m: f"CCTV-{m.group(1)}", name)
            
            # 移除特殊字符
            name = re.sub(r'[·|_（）【】\s]+', ' ', name)
            
            return name.strip()
        except:
            return name.strip() if name else ""

    def fetch_sources(self):
        """获取所有源（本地优先）"""
        sources = []
        
        # 优先加载本地源
        if os.path.exists(LOCAL_SOURCE):
            try:
                with open(LOCAL_SOURCE, 'r', encoding='utf-8') as f:
                    local_content = f.read()
                    sources.append(local_content)
                    print(f"✅ 已加载本地源: {len(local_content.splitlines())}行")
            except Exception as e:
                print(f"⚠️ 读取本地源失败: {e}")
        else:
            print("ℹ️ 本地源文件不存在，跳过")

        # 补充网络源
        if URLS:
            print("🌐 抓取网络源...")
            successful_urls = []
            
            with tqdm(URLS, desc="进度", ncols=80) as pbar:
                for url in pbar:
                    if self.is_blocked(url):
                        pbar.write(f"🚫 跳过黑名单URL: {url.split('/')[-1]}")
                        continue
                    
                    if content := self.fetch_url(url):
                        sources.append(content)
                        successful_urls.append(url.split('/')[-1])
                    else:
                        pbar.write(f"⚠️ 获取失败: {url.split('/')[-1]}")
                    
                    pbar.update(1)
            
            if successful_urls:
                print(f"✅ 成功获取 {len(successful_urls)} 个网络源")
        
        return "\n".join(sources) if sources else ""

    def fetch_url(self, url):
        """抓取单个URL内容"""
        try:
            response = requests.get(url, timeout=15, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            response.encoding = 'utf-8'
            return response.text if response.status_code == 200 else None
        except requests.exceptions.RequestException as e:
            return None
        except Exception as e:
            return None

    def is_blocked(self, url):
        """检查URL是否在黑名单中"""
        try:
            domain = urlparse(url).netloc.split(':')[0].lower()
            return any(kw in domain for kw in self.blacklist)
        except:
            return False

    def parse_sources(self, content):
        """修复版：解析所有源并过滤非模板频道"""
        if not content:
            print("❌ 内容为空，无法解析")
            return defaultdict(list)
            
        channels = defaultdict(list)
        is_m3u = content.startswith("#EXTM3U")
        current_name = None  # 修复：提前初始化变量
        
        print(f"🔍 解析{'M3U' if is_m3u else 'TXT'}格式数据...")
        
        lines = content.splitlines()
        with tqdm(total=len(lines), desc="解析进度", ncols=80) as pbar:
            for line in lines:
                line = line.strip()
                if not line:
                    pbar.update(1)
                    continue
                    
                try:
                    if is_m3u:
                        if line.startswith("#EXTINF"):
                            # 处理M3U格式的频道信息行
                            name_match = re.search(r'tvg-name="([^"]+)"', line)
                            if not name_match:
                                # 尝试其他格式
                                name_match = re.search(r',([^,]+)$', line)
                            
                            if name_match:
                                name = self.clean_name(name_match.group(1))
                                if name in self.template_channels:
                                    current_name = name
                                else:
                                    current_name = None
                        elif line.startswith("http"):
                            # M3U的URL行 - 只有在有频道名时才处理
                            if current_name:
                                channels[current_name].append(line)
                                current_name = None  # 重置
                    else:
                        # 处理TXT格式
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
                finally:
                    pbar.update(1)
        
        # 统计结果
        total_sources = sum(len(urls) for urls in channels.values())
        print(f"✅ 解析完成: {len(channels)}个频道, {total_sources}个源")
        
        return channels

    def speed_test(self, url):
        """增强版测速函数"""
        try:
            start_time = time.time()
            process = subprocess.run([
                "ffmpeg", "-i", url,
                "-t", str(SPEED_TEST_TIMEOUT),
                "-f", "null", "-",
                "-v", "quiet", "-stats"
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=SPEED_TEST_TIMEOUT)
            
            if process.returncode == 0:
                self.success_count += 1
                return {
                    "url": url,
                    "time": (time.time() - start_time) * 1000,
                    "status": "success"
                }
            else:
                self.failed_count += 1
                return {
                    "url": url,
                    "time": SPEED_TEST_TIMEOUT * 1000,
                    "status": "failed"
                }
                
        except subprocess.TimeoutExpired:
            self.failed_count += 1
            return {
                "url": url,
                "time": SPEED_TEST_TIMEOUT * 1000,
                "status": "timeout"
            }
        except Exception as e:
            self.failed_count += 1
            return {
                "url": url,
                "time": float('inf'),
                "status": "error"
            }

    def process_channels(self, channels):
        """处理所有频道（测速+筛选）"""
        if not channels:
            print("❌ 没有可处理的频道数据")
            return []
            
        result = []
        total_channels = len(channels)
        
        print(f"⚡ 开始测速处理 {total_channels} 个频道...")
        
        with tqdm(total=total_channels, desc="🔄 频道处理", ncols=80) as chan_pbar:
            for channel_name, urls in channels.items():
                if not urls:
                    result.append({
                        "name": channel_name,
                        "sources": [],
                        "best_time": None
                    })
                    chan_pbar.update(1)
                    continue
                    
                chan_pbar.set_postfix_str(f"{channel_name[:12]}...")
                
                # 测速当前频道的所有源
                speed_results = []
                with tqdm(urls, desc=f"⏱️ {channel_name[:10]}", leave=False, ncols=60) as url_pbar:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(urls))) as executor:
                        future_to_url = {executor.submit(self.speed_test, url): url for url in urls}
                        for future in concurrent.futures.as_completed(future_to_url):
                            speed_results.append(future.result())
                            url_pbar.update(1)
                
                # 筛选最优源
                valid_sources = [s for s in speed_results if s['status'] == 'success']
                valid_sources.sort(key=lambda x: x['time'])
                best_sources = valid_sources[:MAX_SOURCES]
                
                result.append({
                    "name": channel_name,
                    "sources": best_sources,
                    "best_time": best_sources[0]['time'] if best_sources else None
                })
                chan_pbar.update(1)
        
        # 统计测速结果
        total_tested = self.success_count + self.failed_count
        success_rate = (self.success_count / total_tested * 100) if total_tested > 0 else 0
        print(f"📊 测速统计: 成功 {self.success_count}, 失败 {self.failed_count}, 成功率 {success_rate:.1f}%")
        
        return result

    def generate_output(self, processed_channels):
        """生成输出文件"""
        if not processed_channels:
            print("❌ 没有可输出的数据")
            return
            
        # 统计有效频道
        valid_channels = [c for c in processed_channels if c['sources']]
        print(f"💾 生成输出文件: {len(valid_channels)}个有效频道")
        
        try:
            # 生成TXT文件
            with open(OUTPUT_TXT, 'w', encoding='utf-8') as f:
                # 读取模板结构
                if os.path.exists(TEMPLATE_FILE):
                    with open(TEMPLATE_FILE, 'r', encoding='utf-8') as template_file:
                        template_lines = [line.strip() for line in template_file if line.strip()]
                
                current_genre = "未分类"
                for line in template_lines:
                    if line.endswith(",#genre#"):
                        current_genre = line.replace(",#genre#", "")
                        f.write(f"\n{current_genre},#genre#\n")
                    else:
                        name = self.clean_name(line)
                        channel_data = next((c for c in processed_channels if c['name'] == name), None)
                        if channel_data and channel_data['sources']:
                            for source in channel_data['sources']:
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
                        channel_data = next((c for c in processed_channels if c['name'] == name), None)
                        if channel_data and channel_data['sources']:
                            for source in channel_data['sources']:
                                time_info = f" #响应:{int(source['time'])}ms" if source['time'] < float('inf') else ""
                                f.write(f'#EXTINF:-1 tvg-name="{name}" group-title="{current_genre}",{name}{time_info}\n{source["url"]}\n')
            
            print(f"✅ 文件生成成功: {OUTPUT_TXT}, {OUTPUT_M3U}")
            
        except Exception as e:
            print(f"❌ 文件生成失败: {e}")

# ====================== 主程序 ======================
def main():
    print("🎬 IPTV直播源终极整理工具 - 修复版")
    print(f"🛠️ 配置: 超时{SPEED_TEST_TIMEOUT}s | 保留{MAX_SOURCES}源 | 并发{MAX_WORKERS}线程")
    
    try:
        processor = IPTVProcessor()
        
        # 获取直播源
        content = processor.fetch_sources()
        if not content:
            print("❌ 无法获取直播源数据，程序退出")
            return
        
        # 解析和清洗数据
        channels = processor.parse_sources(content)
        if not channels:
            print("❌ 没有有效的频道数据，程序退出")
            return
        
        # 测速处理
        processed_channels = processor.process_channels(channels)
        
        # 生成输出文件
        processor.generate_output(processed_channels)
        
        print("\n🎉 处理完成！")
        
    except KeyboardInterrupt:
        print("\n⚠️ 用户中断程序")
    except Exception as e:
        print(f"\n❌ 程序执行出错: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
