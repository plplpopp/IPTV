#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
IPTV直播源整理工具 - 精简配置版

功能说明：
1. 从多个来源获取IPTV直播源
2. 自动测速并选择最优源
3. 生成TXT和M3U格式的输出文件
4. 支持HTTP/HTTPS/UDP/RTP协议
5. 支持频道名称清洗和黑名单过滤

使用说明：
1. 确保已安装Python 3和ffmpeg
2. 修改本文件中的配置参数
3. 运行脚本：python iptv.py
"""

import requests
import re
import os
import subprocess
import sys
import logging
from urllib.parse import urlparse
from collections import defaultdict
import concurrent.futures
import time
from tqdm import tqdm

# ====================== 配置区域 ======================
# 直播源URL列表
URLS = [
    "https://raw.githubusercontent.com/Supprise0901/TVBox_live/main/live.txt",
    "https://raw.githubusercontent.com/wwb521/live/main/tv.m3u", 
    "https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/ipv4/result.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/cn.m3u"
]

# 本地直播源文件
LOCAL_SOURCE = "local.txt"

# 黑名单文件
BLACKLIST_FILE = "blacklist.txt"

# 模板文件
TEMPLATE_FILE = "demo.txt"

# 输出文件
OUTPUT_TXT = "iptv.txt"
OUTPUT_M3U = "iptv.m3u"
LOG_FILE = "iptv.log"

# 性能参数
MAX_SOURCES = 8          # 每个频道保留的最大源数量
SPEED_TEST_TIMEOUT = 5   # 测速超时时间(秒)
MAX_WORKERS = 6          # 最大工作线程数
MAX_RETRIES = 3          # 最大重试次数
RETRY_DELAY = 2          # 重试延迟(秒)

# ====================== 日志配置 ======================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ====================== 核心引擎 ======================
class IPTVProcessor:
    def __init__(self):
        """初始化IPTV处理器"""
        self.template_channels = set()  # 模板频道集合
        self.blacklist = self.load_blacklist()  # 加载黑名单
        self.load_template()  # 加载模板
        self.check_ffmpeg()  # 检查ffmpeg

    def check_ffmpeg(self):
        """检查ffmpeg是否可用"""
        try:
            subprocess.run(
                ["ffmpeg", "-version"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
        except Exception as e:
            logger.error("未找到ffmpeg或版本不兼容，请先安装ffmpeg并加入PATH")
            sys.exit(1)

    def load_blacklist(self):
        """加载黑名单"""
        blacklist = []
        if os.path.exists(BLACKLIST_FILE):
            try:
                with open(BLACKLIST_FILE, 'r', encoding='utf-8') as f:
                    blacklist = [line.strip().lower() for line in f if line.strip() and not line.startswith('#')]
            except Exception as e:
                logger.error(f"加载黑名单失败: {e}")
        return blacklist

    def load_template(self):
        """加载模板频道"""
        if os.path.exists(TEMPLATE_FILE):
            try:
                with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.endswith(",#genre#"):
                            cleaned = self.clean_name(line)
                            if cleaned:
                                self.template_channels.add(cleaned)
            except Exception as e:
                logger.error(f"加载模板文件失败: {e}")
        else:
            logger.warning("未找到模板文件，将处理所有频道")

    def clean_name(self, name):
        """清洗频道名称"""
        if not name:
            return ""
        
        try:
            # 标准化CCTV频道名称
            name = re.sub(r'CCTV[\s\-_]?(\d+)', lambda m: f"CCTV-{m.group(1)}", name, flags=re.IGNORECASE)
            # 去除特殊字符
            name = re.sub(r'[·|_（）【】\s]+', ' ', name)
            # 去除多余空格
            name = ' '.join(name.split())
            return name.strip()
        except Exception as e:
            logger.warning(f"清洗频道名称失败: {name}, 错误: {e}")
            return name.strip()

    def fetch_sources(self):
        """获取直播源"""
        sources = []
        
        # 本地源
        if os.path.exists(LOCAL_SOURCE):
            try:
                with open(LOCAL_SOURCE, 'r', encoding='utf-8') as f:
                    sources.append(f.read())
            except Exception as e:
                logger.error(f"读取本地源失败: {e}")
        
        # 网络源
        if URLS:
            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                future_to_url = {executor.submit(self.fetch_url_with_retry, url): url for url in URLS}
                for future in concurrent.futures.as_completed(future_to_url):
                    url = future_to_url[future]
                    try:
                        content = future.result()
                        if content:
                            sources.append(content)
                    except Exception as e:
                        logger.error(f"获取URL内容失败: {url}, 错误: {e}")
        
        return "\n".join(sources)

    def fetch_url_with_retry(self, url):
        """带重试的URL获取"""
        for attempt in range(MAX_RETRIES):
            try:
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    return response.text
            except Exception as e:
                if attempt == MAX_RETRIES - 1:
                    raise
                time.sleep(RETRY_DELAY)
        return None

    def is_blocked(self, url):
        """检查黑名单"""
        try:
            domain = urlparse(url).netloc.lower()
            return any(kw in domain for kw in self.blacklist)
        except Exception as e:
            logger.warning(f"URL解析失败: {url}, 错误: {e}")
            return False

    def parse_sources(self, content):
        """解析M3U/TXT格式数据"""
        if not content:
            return defaultdict(list)
            
        channels = defaultdict(list)
        is_m3u = content.strip().startswith("#EXTM3U")
        current_name = None
        
        logger.info(f"解析{'M3U' if is_m3u else 'TXT'}格式数据...")
        
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
                
            try:
                if is_m3u:
                    if line.startswith("#EXTINF"):
                        name = self.extract_name_from_extinf(line)
                        if name and (not self.template_channels or name in self.template_channels):
                            current_name = name
                        else:
                            current_name = None
                    elif line.startswith(('http://', 'https://', 'udp://', 'rtp://')) and current_name:
                        channels[current_name].append(line)
                        current_name = None
                else:
                    if ',' in line and not line.endswith(",#genre#"):
                        parts = line.split(',', 1)
                        if len(parts) == 2:
                            name, url = parts[0].strip(), parts[1].strip()
                            if url.startswith(('http://', 'https://', 'udp://', 'rtp://')):
                                name = self.clean_name(name)
                                if not self.template_channels or name in self.template_channels:
                                    channels[name].append(url)
            except Exception as e:
                logger.warning(f"解析行失败: {line}, 错误: {e}")
                continue
        
        logger.info(f"解析完成: {len(channels)}个频道")
        return channels

    def extract_name_from_extinf(self, extinf_line):
        """从EXTINF行提取频道名称"""
        try:
            # 方法1: 从tvg-name属性提取
            if match := re.search(r'tvg-name="([^"]+)"', extinf_line):
                return self.clean_name(match.group(1))
            
            # 方法2: 从逗号后的名称提取
            if match := re.search(r',([^,]+)$', extinf_line):
                return self.clean_name(match.group(1))
            
            # 方法3: 从group-title和名称组合提取
            if match := re.search(r'group-title="[^"]*",(.+)$', extinf_line):
                return self.clean_name(match.group(1))
                
        except Exception as e:
            logger.warning(f"EXTINF行解析失败: {extinf_line}, 错误: {e}")
        
        return None

    def speed_test(self, url):
        """测速函数"""
        try:
            start = time.time()
            
            if url.startswith(('http://', 'https://')):
                # HTTP协议使用ffmpeg测试
                subprocess.run([
                    "ffmpeg", "-i", url, "-t", str(SPEED_TEST_TIMEOUT),
                    "-f", "null", "-", "-v", "quiet", "-stats"
                ], check=True, timeout=SPEED_TEST_TIMEOUT, 
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                
                elapsed = (time.time() - start) * 1000
                return {"url": url, "time": elapsed, "status": "success"}
            
            elif url.startswith(('udp://', 'rtp://')):
                # UDP/RTP协议简单测试
                start = time.time()
                try:
                    subprocess.run([
                        "ffplay", "-i", url, "-t", "3", "-autoexit", "-nodisp",
                        "-loglevel", "quiet"
                    ], timeout=3, check=True)
                    elapsed = (time.time() - start) * 1000
                    return {"url": url, "time": elapsed, "status": "success"}
                except:
                    return {"url": url, "time": float('inf'), "status": "error"}
            
            else:
                return {"url": url, "time": float('inf'), "status": "unsupported"}
                
        except subprocess.TimeoutExpired:
            return {"url": url, "time": SPEED_TEST_TIMEOUT*1000, "status": "timeout"}
        except Exception as e:
            logger.warning(f"测速失败: {url}, 错误: {e}")
            return {"url": url, "time": float('inf'), "status": "error"}

    def process_channels(self, channels):
        """处理频道测速"""
        result = []
        total_channels = len(channels)
        
        logger.info(f"开始测速 {total_channels} 个频道...")
        
        with tqdm(total=total_channels, desc="测速进度") as pbar:
            for name, urls in channels.items():
                # 测速所有源
                speed_results = []
                with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                    futures = [executor.submit(self.speed_test, url) for url in urls]
                    for future in futures:
                        speed_results.append(future.result())
                
                # 筛选最优源
                valid_sources = [s for s in speed_results if s['status'] == 'success']
                valid_sources.sort(key=lambda x: x['time'])
                best_sources = valid_sources[:MAX_SOURCES]
                
                result.append({
                    "name": name,
                    "sources": best_sources,
                    "best_time": best_sources[0]['time'] if best_sources else None
                })
                
                pbar.update(1)
        
        return result

    def validate_output(self, processed_channels):
        """验证输出结果"""
        if not processed_channels:
            logger.error("没有有效的频道数据")
            return False
        
        valid_channels = [c for c in processed_channels if c['sources']]
        if not valid_channels:
            logger.error("所有频道测速失败")
            return False
        
        logger.info(f"验证通过: 共 {len(valid_channels)} 个有效频道")
        return True

    def generate_output(self, processed_channels):
        """生成输出文件"""
        # 读取模板结构
        template_lines = []
        if os.path.exists(TEMPLATE_FILE):
            try:
                with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
                    template_lines = [line.strip() for line in f if line.strip()]
            except Exception as e:
                logger.error(f"读取模板文件失败: {e}")
                template_lines = []
        
        # 生成TXT文件
        try:
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
            logger.info(f"成功生成TXT文件: {OUTPUT_TXT}")
        except Exception as e:
            logger.error(f"生成TXT文件失败: {e}")
        
        # 生成M3U文件
        try:
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
            logger.info(f"成功生成M3U文件: {OUTPUT_M3U}")
        except Exception as e:
            logger.error(f"生成M3U文件失败: {e}")

# ====================== 主程序 ======================
def main():
    logger.info("IPTV直播源整理工具 开始运行")
    
    try:
        processor = IPTVProcessor()
        
        # 获取源数据
        logger.info("开始获取直播源数据...")
        content = processor.fetch_sources()
        if not content:
            logger.error("错误: 无法获取直播源数据")
            return
        
        # 解析数据
        logger.info("开始解析直播源数据...")
        channels = processor.parse_sources(content)
        if not channels:
            logger.error("错误: 没有有效的频道数据")
            return
        
        # 测速处理
        logger.info("开始频道测速处理...")
        processed_channels = processor.process_channels(channels)
        
        # 验证结果
        if not processor.validate_output(processed_channels):
            logger.error("输出验证失败，请检查日志")
            return
        
        # 生成输出
        logger.info("开始生成输出文件...")
        processor.generate_output(processed_channels)
        
        logger.info("处理完成!")
    except Exception as e:
        logger.error(f"程序运行出错: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
