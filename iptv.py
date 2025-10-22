#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import pandas as pd
import re
import os
import subprocess
import json
import time
import threading
import hashlib
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import sys
import socket
from urllib.parse import urlparse

# ============================ 配置文件 ============================

# 源配置
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

# 功能开关
ENABLE_FFMPEG = True              # FFmpeg测速开关
ENABLE_SPEED_TEST = True          # 智能测速开关  
ENABLE_RESPONSE_TEST = True       # 响应延时测试开关
ENABLE_TEMPLATE_FILTER = True     # 模板过滤开关
ENABLE_BLACKLIST_FILTER = True    # 黑名单过滤开关
ENABLE_SMART_MATCH = True         # 智能频道匹配开关
ENABLE_DUPLICATE_REMOVAL = True   # 去重开关
ENABLE_ADVANCED_ANALYSIS = True   # 高级分析开关

# 权重配置 (总和应为1.0)
SPEED_WEIGHT = 0.35               # 下载速度权重
RESOLUTION_WEIGHT = 0.25          # 分辨率权重
RESPONSE_WEIGHT = 0.20            # 响应时间权重
STABILITY_WEIGHT = 0.15           # 稳定性权重
BITRATE_WEIGHT = 0.05             # 码率权重

# 数量配置
MAX_SOURCES_PER_CHANNEL = 0       # 每个频道最大接口数 (0表示不限制)
FINAL_SOURCES_PER_CHANNEL = 8     # 最终保留接口数
MAX_WORKERS = 6                   # 并发线程数

# 测试配置
TEST_TIMEOUT = 15                 # 测试超时时间(秒)
MAX_RETRIES = 2                   # 最大重试次数
MIN_SCORE_THRESHOLD = 0.2         # 最低质量分数
SPEED_TEST_DURATION = 5           # 速度测试时长(秒)
CONNECTION_TIMEOUT = 8            # 连接超时时间(秒)

# 质量阈值
MIN_RESOLUTION = 320 * 240        # 最低分辨率
MIN_BITRATE = 500                 # 最低码率(kbps)
MAX_RESPONSE_TIME = 5000          # 最大响应时间(ms)

# 文件配置
LOCAL_SOURCE_FILE = "local.txt"   # 本地源文件
TEMPLATE_FILE = "demo.txt"        # 模板频道文件
BLACKLIST_FILE = "blacklist.txt"  # 黑名单文件
OUTPUT_TXT = "iptv.txt"           # 输出文本文件
OUTPUT_M3U = "iptv.m3u"           # 输出M3U文件
CACHE_FILE = "test_cache.json"    # 测试缓存文件
LOG_FILE = "processing.log"       # 日志文件
QUALITY_REPORT_FILE = "quality_report.json"  # 质量报告文件

# 路径配置
FFMPEG_PATH = "ffmpeg"            # FFmpeg路径

# ============================ 全局变量 ============================

# 正则模式
ipv4_pattern = re.compile(r'^https?://(\d{1,3}\.){3}\d{1,3}')
ipv6_pattern = re.compile(r'^https?://\[([a-fA-F0-9:]+)\]')
domain_pattern = re.compile(r'^https?://([^/:]+)')
channel_pattern = re.compile(r'(.+?)[,\t]\s*(http.+)')

# 存储数据
all_streams = []
test_results = {}
template_channels = []
blacklist_keywords = []
channel_mapping = {}  # 频道名称映射
test_cache = {}       # 测试结果缓存

# ============================ 日志系统 ============================

class Logger:
    def __init__(self, log_file=LOG_FILE):
        self.log_file = log_file
        self.console = sys.stdout
        
    def write(self, message):
        self.console.write(message)
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                if message.strip():
                    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                    f.write(f"[{timestamp}] {message}")
        except Exception as e:
            self.console.write(f"日志写入失败: {e}\n")
    
    def flush(self):
        self.console.flush()

# 重定向标准输出
sys.stdout = Logger()

# ============================ 文件处理函数 ============================

def load_local_sources():
    """加载本地源文件"""
    local_streams = []
    if os.path.exists(LOCAL_SOURCE_FILE):
        print(f"正在加载本地源: {LOCAL_SOURCE_FILE}\n")
        try:
            with open(LOCAL_SOURCE_FILE, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    
                    match = channel_pattern.match(line)
                    if match:
                        program_name = match.group(1).strip()
                        stream_url = match.group(2).strip()
                        local_streams.append({
                            "program_name": program_name,
                            "stream_url": stream_url,
                            "source": "local",
                            "line_num": line_num
                        })
                    else:
                        print(f"  ⚠ 本地源第{line_num}行格式错误: {line}")
            
            print(f"✓ 本地源加载完成: {len(local_streams)} 个频道\n")
        except Exception as e:
            print(f"✗ 本地源加载失败: {e}\n")
    else:
        print(f"ℹ 本地源文件不存在: {LOCAL_SOURCE_FILE}\n")
    return local_streams

def load_template_channels():
    """加载模板频道列表"""
    channels = []
    if os.path.exists(TEMPLATE_FILE):
        print(f"正在加载模板频道: {TEMPLATE_FILE}\n")
        try:
            with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if line and not line.startswith('#'):
                        channels.append(line)
            print(f"✓ 模板频道加载完成: {len(channels)} 个频道\n")
        except Exception as e:
            print(f"✗ 模板频道加载失败: {e}\n")
    else:
        print(f"✗ 模板文件不存在: {TEMPLATE_FILE}\n")
        # 创建示例模板文件
        try:
            with open(TEMPLATE_FILE, 'w', encoding='utf-8') as f:
                f.write("# 模板频道列表\nCCTV-1\nCCTV-2\n湖南卫视\n浙江卫视\n安徽卫视\n")
            print(f"ℹ 已创建示例模板文件: {TEMPLATE_FILE}\n")
        except Exception as e:
            print(f"✗ 创建示例模板文件失败: {e}\n")
    return channels

def load_blacklist():
    """加载黑名单关键词"""
    keywords = []
    if os.path.exists(BLACKLIST_FILE):
        print(f"正在加载黑名单: {BLACKLIST_FILE}\n")
        try:
            with open(BLACKLIST_FILE, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if line and not line.startswith('#'):
                        keywords.append(line.lower())
            print(f"✓ 黑名单加载完成: {len(keywords)} 个关键词\n")
        except Exception as e:
            print(f"✗ 黑名单加载失败: {e}\n")
    else:
        print(f"ℹ 黑名单文件不存在: {BLACKLIST_FILE}\n")
    return keywords

def load_test_cache():
    """加载测试缓存"""
    global test_cache
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                test_cache = json.load(f)
            print(f"✓ 测试缓存加载完成: {len(test_cache)} 条记录\n")
        except Exception as e:
            print(f"✗ 测试缓存加载失败: {e}\n")
            test_cache = {}
    else:
        test_cache = {}
    return test_cache

def save_test_cache():
    """保存测试缓存"""
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(test_cache, f, ensure_ascii=False, indent=2)
        print(f"✓ 测试缓存保存完成: {len(test_cache)} 条记录\n")
    except Exception as e:
        print(f"✗ 测试缓存保存失败: {e}\n")

# ============================ 工具函数 ============================

def get_stream_hash(stream_url):
    """生成流URL的哈希值"""
    return hashlib.md5(stream_url.encode('utf-8')).hexdigest()

def remove_duplicate_streams(streams):
    """去除重复的流"""
    if not ENABLE_DUPLICATE_REMOVAL:
        return streams
    
    seen_urls = set()
    unique_streams = []
    duplicates_removed = 0
    
    for stream in streams:
        stream_hash = get_stream_hash(stream["stream_url"])
        if stream_hash not in seen_urls:
            seen_urls.add(stream_hash)
            unique_streams.append(stream)
        else:
            duplicates_removed += 1
    
    if duplicates_removed > 0:
        print(f"✓ 去重完成: 移除 {duplicates_removed} 个重复流\n")
    
    return unique_streams

def get_protocol_type(url):
    """获取流协议类型"""
    try:
        parsed = urlparse(url)
        protocol = parsed.scheme.lower()
        if 'm3u8' in url.lower():
            return 'HLS'
        elif 'rtmp' in url.lower():
            return 'RTMP'
        elif 'rtsp' in url.lower():
            return 'RTSP'
        elif 'flv' in url.lower():
            return 'FLV'
        else:
            return protocol.upper()
    except:
        return 'UNKNOWN'

# ============================ 智能频道匹配函数 ============================

def normalize_channel_name(name):
    """标准化频道名称"""
    if not name:
        return ""
    
    # 转换为小写并移除空格
    normalized = name.lower().replace(' ', '')
    
    # 移除常见后缀
    suffixes = ['hd', '高清', '4k', '超清', 'fhd', 'uhd', 'live', '卫视', '电视台', '频道']
    for suffix in suffixes:
        if normalized.endswith(suffix):
            normalized = normalized[:-len(suffix)]
    
    # 处理CCTV特殊格式
    if 'cctv' in normalized:
        # 移除cctv后的非数字字符，只保留数字
        normalized = re.sub(r'cctv[^\d]*(\d+)', r'cctv\1', normalized)
        # 确保cctv和数字之间没有分隔符
        normalized = normalized.replace('-', '')
    
    return normalized

def build_channel_mapping(template_channels, actual_channels):
    """构建频道名称映射表"""
    mapping = {}
    
    # 标准化模板频道名称
    template_normalized = {}
    for template in template_channels:
        normalized = normalize_channel_name(template)
        template_normalized[normalized] = template
    
    # 对每个实际频道名称寻找最佳匹配
    for actual in actual_channels:
        actual_normalized = normalize_channel_name(actual)
        
        # 寻找最佳匹配的模板频道
        best_match = None
        best_score = 0
        
        for template_norm, template_orig in template_normalized.items():
            # 完全匹配
            if actual_normalized == template_norm:
                best_match = template_orig
                best_score = 1.0
                break
            
            # 包含关系匹配
            if template_norm in actual_normalized or actual_normalized in template_norm:
                score = len(template_norm) / max(len(actual_normalized), len(template_norm))
                if score > best_score:
                    best_match = template_orig
                    best_score = score
        
        # 如果找到匹配且置信度足够高，则建立映射
        if best_match and best_score > 0.6:  # 降低置信度阈值以提高匹配率
            mapping[actual] = best_match
    
    return mapping

def smart_channel_match(streams):
    """智能频道匹配"""
    if not ENABLE_SMART_MATCH or not template_channels:
        return streams
    
    print("开始智能频道匹配...\n")
    
    # 收集所有实际频道名称
    actual_channels = set(stream["program_name"] for stream in streams)
    
    # 构建频道映射表
    global channel_mapping
    channel_mapping = build_channel_mapping(template_channels, actual_channels)
    
    if not channel_mapping:
        print("ℹ 未找到可匹配的频道\n")
        return streams
    
    # 应用频道映射
    matched_streams = []
    unmatched_count = 0
    
    for stream in streams:
        original_name = stream["program_name"]
        if original_name in channel_mapping:
            # 更新为标准化频道名称
            new_name = channel_mapping[original_name]
            stream["original_name"] = original_name  # 保留原始名称
            stream["program_name"] = new_name
            matched_streams.append(stream)
        else:
            unmatched_count += 1
    
    print(f"✓ 频道匹配完成: {len(matched_streams)} 个流已匹配, {unmatched_count} 个流未匹配\n")
    return matched_streams

# ============================ 黑名单过滤函数 ============================

def extract_domain_and_ip(url):
    """从URL中提取域名和IP地址"""
    try:
        # 提取域名
        domain_match = domain_pattern.match(url)
        if not domain_match:
            return "", ""
        
        host = domain_match.group(1)
        
        # 判断是否是IP地址
        if ipv4_pattern.match(url):
            return "", host  # 返回IP地址
        elif ipv6_pattern.match(url):
            return "", host  # 返回IPv6地址
        else:
            return host, ""  # 返回域名
    except Exception as e:
        print(f"URL解析错误: {url}, 错误: {e}")
        return "", ""

def is_blacklisted(url):
    """检查URL是否在黑名单中"""
    if not ENABLE_BLACKLIST_FILTER or not blacklist_keywords:
        return False
    
    try:
        domain, ip = extract_domain_and_ip(url)
        url_lower = url.lower()
        domain_lower = domain.lower()
        
        # 检查完整URL、域名、IP是否在黑名单中
        for keyword in blacklist_keywords:
            keyword_lower = keyword.lower()
            if (keyword_lower in url_lower or 
                (domain and keyword_lower in domain_lower) or 
                (ip and keyword_lower == ip)):
                return True
    except Exception as e:
        print(f"黑名单检查错误: {e}")
    
    return False

# ============================ 网络请求函数 ============================

def fetch_streams_from_url(url):
    """从URL获取直播源数据"""
    print(f"正在爬取: {url}")
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, timeout=15, headers=headers)
        response.encoding = 'utf-8'
        if response.status_code == 200:
            print(f"✓ 成功获取: {len(response.text)} 字符\n")
            return response.text
        else:
            print(f"✗ 获取失败: HTTP {response.status_code}\n")
    except Exception as e:
        print(f"✗ 请求错误: {e}\n")
    return None

def parse_content(content, source_url="unknown"):
    """解析直播源内容"""
    streams = []
    if not content:
        return streams
        
    for line_num, line in enumerate(content.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
            
        match = channel_pattern.match(line)
        if match:
            program_name = match.group(1).strip()
            stream_url = match.group(2).strip()
            
            # 黑名单过滤
            if is_blacklisted(stream_url):
                continue
                
            streams.append({
                "program_name": program_name,
                "stream_url": stream_url,
                "source": source_url,
                "line_num": line_num
            })
    
    return streams

def fetch_all_online_sources():
    """获取所有在线源"""
    online_streams = []
    print("开始获取在线源...\n")
    
    for url in URLS:
        if content := fetch_streams_from_url(url):
            streams = parse_content(content, url)
            online_streams.extend(streams)
            print(f"  ✓ 从 {url} 获取 {len(streams)} 个流\n")
        else:
            print(f"  ✗ 跳过: {url}\n")
    
    return online_streams

# ============================ 增强测速函数 ============================

def test_connection_speed(stream_url):
    """测试连接速度和稳定性"""
    if not ENABLE_SPEED_TEST:
        return {"speed_score": 0, "stability": 0, "bitrate": 0}
    
    try:
        # 使用curl进行更精确的速度测试
        cmd = [
            'curl', '-o', '/dev/null',
            '--max-time', str(SPEED_TEST_DURATION),
            '--connect-timeout', str(CONNECTION_TIMEOUT),
            '--write-out', '%{speed_download} %{time_total} %{http_code}',
            '--silent',
            stream_url
        ]
        
        start_time = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=SPEED_TEST_DURATION + 5)
        total_time = time.time() - start_time
        
        if result.returncode == 0:
            output_parts = result.stdout.strip().split()
            if len(output_parts) >= 3:
                speed_bps = float(output_parts[0])  # 字节/秒
                time_total = float(output_parts[1])
                http_code = int(output_parts[2])
                
                if http_code == 200:
                    speed_kbps = (speed_bps * 8) / 1024  # 转换为kbps
                    
                    # 计算稳定性分数（基于完成时间与预期时间的比例）
                    stability = min(1.0, SPEED_TEST_DURATION / total_time) if total_time > 0 else 0
                    
                    # 速度分数（归一化到0-1，10Mbps为满分）
                    speed_score = min(1.0, speed_kbps / 10240)
                    
                    # 估算码率（基于下载速度）
                    estimated_bitrate = speed_kbps * 0.8  # 假设80%为有效码率
                    
                    return {
                        "speed_score": speed_score,
                        "stability": stability,
                        "bitrate": estimated_bitrate,
                        "actual_speed_kbps": speed_kbps
                    }
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, ValueError):
        pass
    
    return {"speed_score": 0, "stability": 0, "bitrate": 0}

def test_stream_response_time(stream_url):
    """增强版响应时间测试"""
    if not ENABLE_RESPONSE_TEST:
        return 0
    
    response_times = []
    
    for retry in range(MAX_RETRIES):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Range': 'bytes=0-1024'  # 请求少量数据
            }
            start_time = time.time()
            response = requests.get(stream_url, timeout=TEST_TIMEOUT, 
                                  allow_redirects=True, headers=headers, stream=True)
            
            # 读取前1KB数据来测试真实响应
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    response_time = (time.time() - start_time) * 1000
                    response_times.append(response_time)
                    break
                    
            response.close()
            
            if response.status_code in [200, 206]:
                break
                
        except Exception:
            if retry == MAX_RETRIES - 1:
                response_times.append(MAX_RESPONSE_TIME)
        time.sleep(0.5)
    
    # 返回最佳（最小）响应时间
    return min(response_times) if response_times else MAX_RESPONSE_TIME

def analyze_stream_with_ffmpeg(stream_url):
    """使用FFmpeg深度分析流信息"""
    if not ENABLE_FFMPEG:
        return {"resolution": 0, "bitrate": 0, "codec": "unknown", "protocol": get_protocol_type(stream_url)}
    
    # 检查ffmpeg是否可用
    try:
        subprocess.run([FFMPEG_PATH, '-version'], capture_output=True, timeout=5, check=True)
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        return {"resolution": 0, "bitrate": 0, "codec": "unknown", "protocol": get_protocol_type(stream_url)}
    
    try:
        # 使用更详细的FFmpeg分析
        cmd = [
            FFMPEG_PATH, '-i', stream_url,
            '-t', '8',  # 延长分析时间到8秒
            '-f', 'null', '-',
            '-hide_banner', '-loglevel', 'info'
        ]
        
        start_time = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        analysis_time = time.time() - start_time
        
        output = result.stderr
        
        # 解析分辨率
        resolution = 0
        if match := re.search(r'(\d+)x(\d+)', output):
            w, h = int(match.group(1)), int(match.group(2))
            resolution = w * h
        
        # 解析码率
        bitrate = 0
        if match := re.search(r'bitrate:\s*(\d+)\s*kb/s', output):
            bitrate = int(match.group(1))
        
        # 解析视频编码
        codec = "unknown"
        if match := re.search(r'Video:\s*([^,]+)', output):
            codec = match.group(1).strip()
        
        # 计算分析成功率
        analysis_success = 1.0 if analysis_time > 5 else analysis_time / 5
        
        return {
            "resolution": resolution,
            "bitrate": bitrate,
            "codec": codec,
            "protocol": get_protocol_type(stream_url),
            "analysis_success": analysis_success
        }
        
    except subprocess.TimeoutExpired:
        return {"resolution": 0, "bitrate": 0, "codec": "unknown", "protocol": get_protocol_type(stream_url), "analysis_success": 0}
    except Exception as e:
        return {"resolution": 0, "bitrate": 0, "codec": "unknown", "protocol": get_protocol_type(stream_url), "analysis_success": 0}

def calculate_advanced_score(stream_data):
    """计算增强版综合得分"""
    try:
        speed_score = stream_data.get("speed_score", 0)
        resolution = stream_data.get("resolution", 0)
        response_time = stream_data.get("response_time", MAX_RESPONSE_TIME)
        stability = stream_data.get("stability", 0)
        bitrate = stream_data.get("bitrate", 0)
        analysis_success = stream_data.get("analysis_success", 0)
        
        # 归一化处理
        norm_speed = speed_score  # 已经是0-1
        norm_resolution = min(resolution / (1920*1080), 1.0) if resolution >= MIN_RESOLUTION else 0
        norm_response = max(0, 1 - (response_time / MAX_RESPONSE_TIME))
        norm_stability = stability
        norm_bitrate = min(bitrate / 8000, 1.0) if bitrate >= MIN_BITRATE else 0
        
        # 基础质量分数
        base_score = (
            norm_speed * SPEED_WEIGHT +
            norm_resolution * RESOLUTION_WEIGHT +
            norm_response * RESPONSE_WEIGHT +
            norm_stability * STABILITY_WEIGHT +
            norm_bitrate * BITRATE_WEIGHT
        )
        
        # 分析成功率作为质量乘数
        quality_multiplier = 0.5 + (analysis_success * 0.5)
        
        # 协议类型加成
        protocol = stream_data.get("protocol", "UNKNOWN")
        protocol_bonus = {
            'HLS': 1.0,
            'HTTP': 0.9,
            'HTTPS': 0.95,
            'RTMP': 0.8,
            'RTSP': 0.7,
            'FLV': 0.85
        }.get(protocol, 0.5)
        
        final_score = base_score * quality_multiplier * protocol_bonus
        
        # 详细得分信息（用于调试）
        score_details = {
            "base_score": round(base_score, 4),
            "speed": round(norm_speed, 4),
            "resolution": round(norm_resolution, 4),
            "response": round(norm_response, 4),
            "stability": round(norm_stability, 4),
            "bitrate": round(norm_bitrate, 4),
            "quality_multiplier": round(quality_multiplier, 4),
            "protocol_bonus": protocol_bonus,
            "final_score": round(final_score, 4)
        }
        
        stream_data["score_details"] = score_details
        
        return round(final_score, 4)
        
    except Exception as e:
        print(f"计算得分错误: {e}")
        return 0

def test_single_stream_enhanced(stream_info):
    """增强版单流测试"""
    try:
        program_name = stream_info["program_name"]
        stream_url = stream_info["stream_url"]
        stream_hash = get_stream_hash(stream_url)
        
        # 检查缓存
        if stream_hash in test_cache:
            cached_result = test_cache[stream_hash]
            # 检查缓存时间（2小时内有效）
            if time.time() - cached_result.get("timestamp", 0) < 7200:
                print(f"  ♻ 使用缓存: {program_name}")
                return cached_result["result"]
        
        print(f"  🔍 测试中: {program_name}")
        
        # 并行执行不同类型的测试
        with ThreadPoolExecutor(max_workers=3) as executor:
            # 提交测试任务
            future_response = executor.submit(test_stream_response_time, stream_url)
            future_speed = executor.submit(test_connection_speed, stream_url)
            future_analysis = executor.submit(analyze_stream_with_ffmpeg, stream_url)
            
            # 获取结果
            response_time = future_response.result(timeout=TEST_TIMEOUT)
            speed_result = future_speed.result(timeout=SPEED_TEST_DURATION + 5)
            analysis_result = future_analysis.result(timeout=20)
        
        # 合并测试结果
        result = {
            "program_name": program_name,
            "stream_url": stream_url,
            "response_time": response_time,
            "speed_score": speed_result["speed_score"],
            "stability": speed_result["stability"],
            "bitrate": max(speed_result["bitrate"], analysis_result["bitrate"]),
            "resolution": analysis_result["resolution"],
            "codec": analysis_result["codec"],
            "protocol": analysis_result["protocol"],
            "analysis_success": analysis_result.get("analysis_success", 0),
            "actual_speed_kbps": speed_result.get("actual_speed_kbps", 0),
            "score": 0
        }
        
        # 计算综合得分
        result["score"] = calculate_advanced_score(result)
        
        # 更新缓存
        test_cache[stream_hash] = {
            "result": result,
            "timestamp": time.time()
        }
        
        # 显示测试结果摘要
        if result["score"] > MIN_SCORE_THRESHOLD:
            print(f"  ✓ 测试完成: {program_name} - 得分: {result['score']:.3f} "
                  f"(响应: {response_time:.0f}ms, 速度: {result['actual_speed_kbps']:.0f}kbps, "
                  f"分辨率: {result['resolution']})")
        else:
            print(f"  ✗ 质量过低: {program_name} - 得分: {result['score']:.3f}")
        
        return result
        
    except Exception as e:
        print(f"  ✗ 测试失败: {stream_info.get('program_name', 'Unknown')}, 错误: {e}")
        return None

def test_all_streams_enhanced(streams):
    """增强版流测试"""
    if not streams:
        return []
    
    print(f"开始增强测试 {len(streams)} 个流...\n")
    
    tested_streams = []
    failed_count = 0
    quality_streams = 0
    
    # 使用tqdm显示进度条
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 提交所有任务
        future_to_stream = {
            executor.submit(test_single_stream_enhanced, stream): stream 
            for stream in streams
        }
        
        # 使用tqdm创建进度条
        with tqdm(total=len(streams), desc="测试进度", unit="流", 
                 bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]") as pbar:
            for future in as_completed(future_to_stream):
                try:
                    result = future.result(timeout=TEST_TIMEOUT + 10)
                    if result and result["score"] >= MIN_SCORE_THRESHOLD:
                        tested_streams.append(result)
                        quality_streams += 1
                    else:
                        failed_count += 1
                except Exception as e:
                    failed_count += 1
                finally:
                    pbar.update(1)
    
    print(f"\n✓ 增强测试完成!")
    print(f"  - 总测试: {len(streams)}")
    print(f"  - 优质流: {quality_streams} (得分 ≥ {MIN_SCORE_THRESHOLD})")
    print(f"  - 失败/低质: {failed_count}")
    print(f"  - 成功率: {quality_streams/len(streams)*100:.1f}%\n")
    
    return tested_streams

# ============================ 数据处理函数 ============================

def filter_by_template(streams):
    """根据模板过滤频道"""
    if not ENABLE_TEMPLATE_FILTER or not template_channels:
        print("ℹ 模板过滤已禁用或模板为空\n")
        return streams
    
    # 先进行智能匹配
    if ENABLE_SMART_MATCH:
        streams = smart_channel_match(streams)
    
    # 然后进行精确过滤
    filtered_streams = []
    template_set = set(template_channels)
    
    for stream in streams:
        if stream["program_name"] in template_set:
            filtered_streams.append(stream)
    
    print(f"✓ 模板过滤: {len(filtered_streams)}/{len(streams)} 个流\n")
    return filtered_streams

def group_and_select_streams(streams):
    """分组并选择最佳流"""
    if not streams:
        return []
    
    # 按频道名分组
    channels_dict = {}
    for stream in streams:
        name = stream["program_name"]
        if name not in channels_dict:
            channels_dict[name] = []
        channels_dict[name].append(stream)
    
    print(f"分组完成: {len(channels_dict)} 个频道\n")
    
    # 对每个频道的流排序并选择最佳
    selected_streams = []
    for channel_name, channel_streams in channels_dict.items():
        # 按得分排序（从高到低）
        sorted_streams = sorted(channel_streams, key=lambda x: x.get("score", 0), reverse=True)
        
        # 如果设置了最大接口数限制，则截取前N个
        if MAX_SOURCES_PER_CHANNEL > 0:
            selected = sorted_streams[:MAX_SOURCES_PER_CHANNEL]
        else:
            selected = sorted_streams  # 不限制数量
            
        selected_streams.extend(selected)
    
    return selected_streams

def sort_by_template(streams):
    """按照模板顺序排序"""
    if not template_channels:
        return streams
    
    # 创建模板顺序映射
    template_order = {name: idx for idx, name in enumerate(template_channels)}
    
    # 按照模板顺序排序，不在模板中的放在最后
    return sorted(streams, key=lambda x: template_order.get(x["program_name"], 9999))

# ============================ 质量报告函数 ============================

def generate_quality_report(streams):
    """生成质量报告"""
    if not streams:
        return
    
    print("生成质量分析报告...\n")
    
    report = {
        "generated_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_streams": len(streams),
        "channels": {},
        "quality_stats": {
            "score_distribution": {"excellent": 0, "good": 0, "fair": 0, "poor": 0},
            "protocol_distribution": {},
            "resolution_distribution": {}
        }
    }
    
    # 分析每个频道
    for stream in streams:
        channel = stream["program_name"]
        if channel not in report["channels"]:
            report["channels"][channel] = []
        
        stream_info = {
            "url": stream["stream_url"],
            "score": stream["score"],
            "response_time": stream["response_time"],
            "speed_kbps": stream.get("actual_speed_kbps", 0),
            "resolution": stream["resolution"],
            "bitrate": stream["bitrate"],
            "protocol": stream["protocol"],
            "codec": stream["codec"]
        }
        report["channels"][channel].append(stream_info)
        
        # 质量分布
        score = stream["score"]
        if score >= 0.8:
            report["quality_stats"]["score_distribution"]["excellent"] += 1
        elif score >= 0.6:
            report["quality_stats"]["score_distribution"]["good"] += 1
        elif score >= 0.4:
            report["quality_stats"]["score_distribution"]["fair"] += 1
        else:
            report["quality_stats"]["score_distribution"]["poor"] += 1
        
        # 协议分布
        protocol = stream["protocol"]
        report["quality_stats"]["protocol_distribution"][protocol] = \
            report["quality_stats"]["protocol_distribution"].get(protocol, 0) + 1
        
        # 分辨率分布
        res = stream["resolution"]
        if res >= 1920*1080:
            res_key = "1080p+"
        elif res >= 1280*720:
            res_key = "720p"
        elif res >= 1024*576:
            res_key = "576p"
        elif res >= 720*480:
            res_key = "480p"
        else:
            res_key = "SD"
        report["quality_stats"]["resolution_distribution"][res_key] = \
            report["quality_stats"]["resolution_distribution"].get(res_key, 0) + 1
    
    # 保存报告
    try:
        with open(QUALITY_REPORT_FILE, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"✓ 质量报告已保存: {QUALITY_REPORT_FILE}\n")
        
        # 显示简要统计
        stats = report["quality_stats"]
        print("质量分布统计:")
        print(f"  - 优秀(≥0.8): {stats['score_distribution']['excellent']} 个")
        print(f"  - 良好(≥0.6): {stats['score_distribution']['good']} 个")
        print(f"  - 一般(≥0.4): {stats['score_distribution']['fair']} 个")
        print(f"  - 较差(<0.4): {stats['score_distribution']['poor']} 个")
        print(f"协议分布: {dict(stats['protocol_distribution'])}")
        print(f"分辨率分布: {dict(stats['resolution_distribution'])}\n")
        
    except Exception as e:
        print(f"✗ 质量报告生成失败: {e}\n")

# ============================ 输出函数 ============================

def save_to_txt(streams):
    """保存为TXT格式"""
    print(f"保存到: {OUTPUT_TXT}\n")
    
    if not streams:
        print("✗ 没有数据可保存\n")
        return
    
    # 按频道分组
    channels_dict = {}
    for stream in streams:
        name = stream["program_name"]
        if name not in channels_dict:
            channels_dict[name] = []
        channels_dict[name].append({
            "url": stream["stream_url"],
            "score": stream.get("score", 0),
            "response_time": stream.get("response_time", 0),
            "speed": stream.get("actual_speed_kbps", 0)
        })
    
    try:
        with open(OUTPUT_TXT, 'w', encoding='utf-8') as f:
            # 写入文件头
            f.write("# IPTV直播源 - 自动生成（增强版）\n")
            f.write(f"# 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# 频道数量: {len(channels_dict)}\n")
            f.write(f"# 流数量: {len(streams)}\n")
            f.write("# 格式: 频道名称,直播流URL,质量得分,响应时间(ms),速度(kbps)\n\n")
            
            total_channels = 0
            total_streams = 0
            
            # 按模板顺序写入
            for channel_name in template_channels:
                if channel_name in channels_dict:
                    # 按得分排序并限制数量
                    streams_list = sorted(channels_dict[channel_name], 
                                        key=lambda x: x["score"], reverse=True)
                    if FINAL_SOURCES_PER_CHANNEL > 0:
                        streams_list = streams_list[:FINAL_SOURCES_PER_CHANNEL]
                    
                    for stream_info in streams_list:
                        f.write(f"{channel_name},{stream_info['url']},"
                               f"{stream_info['score']:.3f},{stream_info['response_time']:.0f},"
                               f"{stream_info['speed']:.0f}\n")
                    
                    total_channels += 1
                    total_streams += len(streams_list)
            
        print(f"✓ TXT文件保存成功: {total_channels} 个频道, {total_streams} 个流\n")
        
    except Exception as e:
        print(f"✗ TXT文件保存失败: {e}\n")

def save_to_m3u(streams):
    """保存为M3U格式"""
    print(f"保存到: {OUTPUT_M3U}\n")
    
    if not streams:
        print("✗ 没有数据可保存\n")
        return
    
    # 按频道分组
    channels_dict = {}
    for stream in streams:
        name = stream["program_name"]
        if name not in channels_dict:
            channels_dict[name] = []
        channels_dict[name].append({
            "url": stream["stream_url"],
            "score": stream.get("score", 0),
            "response_time": stream.get("response_time", 0)
        })
    
    try:
        with open(OUTPUT_M3U, 'w', encoding='utf-8') as f:
            f.write("#EXTM3U\n")
            f.write(f"# Generated by Enhanced IPTV Processor on {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# Total Channels: {len(channels_dict)}\n")
            f.write(f"# Total Streams: {len(streams)}\n\n")
            
            total_channels = 0
            total_streams = 0
            
            # 按模板顺序写入
            for channel_name in template_channels:
                if channel_name in channels_dict:
                    # 按得分排序并限制数量
                    streams_list = sorted(channels_dict[channel_name], 
                                        key=lambda x: x["score"], reverse=True)
                    if FINAL_SOURCES_PER_CHANNEL > 0:
                        streams_list = streams_list[:FINAL_SOURCES_PER_CHANNEL]
                    
                    for stream_info in streams_list:
                        f.write(f'#EXTINF:-1 tvg-id="{channel_name}" tvg-name="{channel_name}" '
                               f'group-title="Live" tvg-logo="",{channel_name} '
                               f'(得分:{stream_info["score"]:.2f} 响应:{stream_info["response_time"]:.0f}ms)\n')
                        f.write(f'{stream_info["url"]}\n')
                    
                    total_channels += 1
                    total_streams += len(streams_list)
            
        print(f"✓ M3U文件保存成功: {total_channels} 个频道, {total_streams} 个流\n")
            
    except Exception as e:
        print(f"✗ M3U文件保存失败: {e}\n")

def display_channel_stats(streams):
    """显示频道统计信息"""
    if not streams:
        return
    
    channels_dict = {}
    for stream in streams:
        name = stream["program_name"]
        if name not in channels_dict:
            channels_dict[name] = []
        channels_dict[name].append(stream)
    
    print("\n" + "="*70)
    print("频道质量统计:")
    print("="*70)
    
    total_test_streams = 0
    total_final_streams = 0
    avg_scores = []
    
    # 按模板顺序显示
    for channel_name in template_channels:
        if channel_name in channels_dict:
            streams_list = channels_dict[channel_name]
            count = len(streams_list)
            
            # 计算平均得分
            avg_score = sum(s["score"] for s in streams_list) / count
            avg_scores.append(avg_score)
            
            # 限制最终显示数量
            final_count = min(count, FINAL_SOURCES_PER_CHANNEL) if FINAL_SOURCES_PER_CHANNEL > 0 else count
            total_test_streams += count
            total_final_streams += final_count
            
            # 质量评级
            if avg_score >= 0.8:
                quality = "★★★★★"
            elif avg_score >= 0.6:
                quality = "★★★★"
            elif avg_score >= 0.4:
                quality = "★★★"
            else:
                quality = "★★"
                
            print(f"  📺 {channel_name:<15} {quality} 平均得分:{avg_score:.3f} "
                  f"接口:{final_count}/{count}个")
    
    if avg_scores:
        overall_avg = sum(avg_scores) / len(avg_scores)
        print("="*70)
        print(f"总览: {len([c for c in template_channels if c in channels_dict])} 个频道")
        print(f"测试通过流: {total_test_streams} 个")
        print(f"最终保留流: {total_final_streams} 个")
        print(f"整体平均质量: {overall_avg:.3f}")
        print("="*70 + "\n")

def verify_output_files():
    """验证输出文件完整性"""
    print("验证输出文件...\n")
    
    for filename in [OUTPUT_TXT, OUTPUT_M3U]:
        if os.path.exists(filename):
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    valid_lines = [line for line in lines if line.strip() and not line.startswith('#')]
                    print(f"✓ {filename}: {len(valid_lines)} 个有效流")
            except Exception as e:
                print(f"✗ {filename} 验证失败: {e}")
        else:
            print(f"✗ {filename} 不存在")

# ============================ 主函数 ============================

def main():
    """主函数"""
    print("🎬 IPTV直播源智能处理工具 - 增强版")
    print("=" * 60)
    print(f"开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60 + "\n")
    
    start_time = time.time()
    
    try:
        # 加载配置
        global template_channels, blacklist_keywords
        template_channels = load_template_channels()
        blacklist_keywords = load_blacklist()
        load_test_cache()
        
        if ENABLE_TEMPLATE_FILTER and not template_channels:
            print("✗ 错误: 模板过滤已启用但模板为空\n")
            return
        
        # 收集所有源
        all_streams = []
        
        # 优先加载本地源
        local_streams = load_local_sources()
        all_streams.extend(local_streams)
        
        # 加载在线源
        online_streams = fetch_all_online_sources()
        all_streams.extend(online_streams)
        
        if not all_streams:
            print("✗ 错误: 没有找到任何直播源\n")
            return
        
        print(f"✓ 总共收集到: {len(all_streams)} 个流\n")
        
        # 去重处理
        all_streams = remove_duplicate_streams(all_streams)
        
        # 模板过滤（包含智能匹配）
        if ENABLE_TEMPLATE_FILTER:
            all_streams = filter_by_template(all_streams)
        
        if not all_streams:
            print("✗ 错误: 过滤后没有可用的流\n")
            return
        
        # 增强测试所有流
        tested_streams = test_all_streams_enhanced(all_streams)
        
        if not tested_streams:
            print("✗ 错误: 测试后没有可用的流\n")
            return
        
        # 分组选择最佳流
        print("正在选择最佳流...\n")
        selected_streams = group_and_select_streams(tested_streams)
        
        # 按模板排序
        final_streams = sort_by_template(selected_streams)
        
        # 显示统计信息
        display_channel_stats(final_streams)
        
        # 生成质量报告
        generate_quality_report(final_streams)
        
        # 保存文件
        print("正在保存文件...\n")
        save_to_txt(final_streams)
        save_to_m3u(final_streams)
        
        # 验证输出
        verify_output_files()
        
        # 保存缓存
        save_test_cache()
        
        # 计算总耗时
        end_time = time.time()
        total_time = end_time - start_time
        
        print("=" * 60)
        print("🎉 增强版处理完成!")
        print(f"⏱ 总耗时: {total_time:.2f} 秒")
        print(f"📁 输出文件: {OUTPUT_TXT}, {OUTPUT_M3U}")
        print(f"📊 质量报告: {QUALITY_REPORT_FILE}")
        print(f"📝 日志文件: {LOG_FILE}")
        print(f"💾 缓存文件: {CACHE_FILE}")
        print("=" * 60 + "\n")
        
    except KeyboardInterrupt:
        print("\n\n⚠ 用户中断执行")
        # 保存当前缓存
        save_test_cache()
    except Exception as e:
        print(f"\n\n✗ 程序执行出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
