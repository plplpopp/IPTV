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

# 源配置 - 更新为您的URL列表
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
ENABLE_FFMPEG = True              # 开启FFmpeg测速
ENABLE_SPEED_TEST = True          # 智能测速开关  
ENABLE_RESPONSE_TEST = True       # 响应延时测试开关
ENABLE_TEMPLATE_FILTER = True     # 模板过滤开关
ENABLE_BLACKLIST_FILTER = True    # 黑名单过滤开关
ENABLE_SMART_MATCH = True         # 智能频道匹配开关
ENABLE_DUPLICATE_REMOVAL = True   # 去重开关

# 数量配置
MAX_SOURCES_PER_CHANNEL = 0       # 每个频道最大接口数 (0表示不限制)
FINAL_SOURCES_PER_CHANNEL = 5     # 最终保留接口数
MAX_WORKERS = 6                   # 并发线程数

# 测试配置
TEST_TIMEOUT = 8                  # 测试超时时间(秒)
SPEED_TEST_DURATION = 5           # 速度测试时长(秒)
CONNECTION_TIMEOUT = 5            # 连接超时时间(秒)
FFMPEG_DURATION = 6               # FFmpeg分析时长(秒)

# 文件配置
LOCAL_SOURCE_FILE = "local.txt"   # 本地源文件
TEMPLATE_FILE = "demo.txt"        # 模板频道文件
BLACKLIST_FILE = "blacklist.txt"  # 黑名单文件
OUTPUT_TXT = "iptv.txt"           # 输出文本文件
OUTPUT_M3U = "iptv.m3u"           # 输出M3U文件

# 路径配置
FFMPEG_PATH = "ffmpeg"            # FFmpeg路径

# ============================ 全局变量 ============================

# 正则模式
ipv4_pattern = re.compile(r'^https?://(\d{1,3}\.){3}\d{1,3}')
ipv6_pattern = re.compile(r'^https?://\[([a-fA-F0-9:]+)\]')
domain_pattern = re.compile(r'^https?://([^/:]+)')
channel_pattern = re.compile(r'(.+?)[,\t]\s*(http.+)')
m3u_channel_pattern = re.compile(r'#EXTINF:.+?,(.+?)\s*(?:\(.*?\))?\s*\n(http.+)', re.IGNORECASE)

# 存储数据
all_streams = []
test_results = {}
template_channels = []
blacklist_keywords = []
channel_mapping = {}  # 频道名称映射

# ============================ 文件处理函数 ============================

def load_local_sources():
    """加载本地源文件"""
    local_streams = []
    if os.path.exists(LOCAL_SOURCE_FILE):
        print(f"正在加载本地源: {LOCAL_SOURCE_FILE}")
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
        print(f"正在加载模板频道: {TEMPLATE_FILE}")
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
        print(f"正在加载黑名单: {BLACKLIST_FILE}")
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
                score = len(template_norm) / max(len(actual_normalized), len(ttemplate_norm))
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
    
    print("开始智能频道匹配...")
    
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
            print(f"✓ 成功获取: {len(response.text)} 字符")
            return response.text
        else:
            print(f"✗ 获取失败: HTTP {response.status_code}")
    except Exception as e:
        print(f"✗ 请求错误: {e}")
    return None

def parse_m3u_content(content, source_url="unknown"):
    """解析M3U格式内容"""
    streams = []
    if not content:
        return streams
    
    try:
        # 匹配M3U格式： #EXTINF:... 和 URL
        lines = content.splitlines()
        i = 0
        while i < len(lines) - 1:
            line = lines[i].strip()
            if line.startswith('#EXTINF:'):
                # 提取频道名称
                channel_name_match = re.search(r'#EXTINF:.*?,(.+)', line)
                if channel_name_match:
                    channel_name = channel_name_match.group(1).strip()
                    # 清理频道名称中的额外信息
                    channel_name = re.sub(r'\s*\(.*?\)\s*', '', channel_name)
                    
                    # 下一行应该是URL
                    if i + 1 < len(lines):
                        url_line = lines[i + 1].strip()
                        if url_line and not url_line.startswith('#'):
                            stream_url = url_line
                            
                            # 黑名单过滤
                            if not is_blacklisted(stream_url):
                                streams.append({
                                    "program_name": channel_name,
                                    "stream_url": stream_url,
                                    "source": source_url,
                                    "line_num": i + 1
                                })
                            i += 1  # 跳过URL行
            i += 1
    except Exception as e:
        print(f"解析M3U内容错误: {e}")
    
    return streams

def parse_txt_content(content, source_url="unknown"):
    """解析TXT格式内容"""
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
            if not is_blacklisted(stream_url):
                streams.append({
                    "program_name": program_name,
                    "stream_url": stream_url,
                    "source": source_url,
                    "line_num": line_num
                })
    
    return streams

def parse_content(content, source_url="unknown"):
    """自动检测并解析内容格式"""
    streams = []
    if not content:
        return streams
    
    # 检测格式类型
    if content.startswith('#EXTM3U'):
        # M3U格式
        streams = parse_m3u_content(content, source_url)
    else:
        # TXT格式
        streams = parse_txt_content(content, source_url)
    
    return streams

def fetch_all_online_sources():
    """获取所有在线源"""
    online_streams = []
    print("开始获取在线源...")
    
    successful_sources = 0
    failed_sources = 0
    
    for url in URLS:
        if content := fetch_streams_from_url(url):
            streams = parse_content(content, url)
            online_streams.extend(streams)
            print(f"  ✓ 从 {url} 获取 {len(streams)} 个流")
            successful_sources += 1
        else:
            print(f"  ✗ 跳过: {url}")
            failed_sources += 1
        print()  # 空行分隔
    
    print(f"在线源获取完成: {successful_sources} 成功, {failed_sources} 失败\n")
    return online_streams

# ============================ 测速函数（无质量过滤） ============================

def test_connection_speed(stream_url):
    """连接速度测试"""
    if not ENABLE_SPEED_TEST:
        return {"actual_speed_kbps": 0, "success": False}
    
    try:
        # 使用requests进行速度测试
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Range': 'bytes=0-51200'  # 请求50KB数据
        }
        
        start_time = time.time()
        response = requests.get(stream_url, timeout=SPEED_TEST_DURATION, 
                              headers=headers, stream=True)
        
        total_bytes = 0
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                total_bytes += len(chunk)
                if total_bytes >= 51200:  # 收到50KB数据就停止
                    break
        
        download_time = time.time() - start_time
        response.close()
        
        if download_time > 0 and total_bytes > 0:
            speed_kbps = (total_bytes * 8) / download_time / 1024
            return {
                "actual_speed_kbps": speed_kbps,
                "success": True,
                "bytes_received": total_bytes
            }
    
    except Exception as e:
        pass
    
    return {"actual_speed_kbps": 0, "success": False}

def test_stream_response_time(stream_url):
    """响应时间测试"""
    if not ENABLE_RESPONSE_TEST:
        return 99999  # 返回一个很大的值表示未测试
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        start_time = time.time()
        response = requests.head(stream_url, timeout=TEST_TIMEOUT, 
                               allow_redirects=True, headers=headers)
        response_time = (time.time() - start_time) * 1000
        
        if response.status_code in [200, 301, 302, 307]:
            return response_time
            
    except Exception:
        pass
    
    return 99999  # 返回一个很大的值表示测试失败

def analyze_stream_with_ffmpeg(stream_url):
    """FFmpeg流分析 - 只用于测速，不检查任何质量"""
    if not ENABLE_FFMPEG:
        return {"ffmpeg_success": False, "protocol": get_protocol_type(stream_url)}
    
    # 检查ffmpeg是否可用
    try:
        subprocess.run([FFMPEG_PATH, '-version'], capture_output=True, timeout=3, check=True)
    except:
        return {"ffmpeg_success": False, "protocol": get_protocol_type(stream_url)}
    
    try:
        # FFmpeg分析命令 - 用于测试流可用性
        cmd = [
            FFMPEG_PATH,
            '-i', stream_url,
            '-t', '4',  # 分析4秒
            '-f', 'null',
            '-',
            '-hide_banner',
            '-loglevel', 'error'
        ]
        
        start_time = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        analysis_time = time.time() - start_time
        
        # 如果FFmpeg成功运行且没有报错，认为流可用
        ffmpeg_success = result.returncode == 0 and analysis_time > 2
        
        # 从输出中尝试获取一些基本信息（但不用于过滤）
        codec = "unknown"
        has_video = False
        
        for line in result.stderr.split('\n'):
            if 'Video:' in line:
                has_video = True
                codec_match = re.search(r'Video:\s*([^,]+)', line)
                if codec_match:
                    codec = codec_match.group(1).strip()
        
        return {
            "ffmpeg_success": ffmpeg_success,
            "analysis_time": analysis_time,
            "has_video": has_video,
            "codec": codec,
            "protocol": get_protocol_type(stream_url)
        }
        
    except subprocess.TimeoutExpired:
        return {"ffmpeg_success": False, "protocol": get_protocol_type(stream_url)}
    except Exception:
        return {"ffmpeg_success": False, "protocol": get_protocol_type(stream_url)}

def is_stream_acceptable(test_result):
    """判断流是否可接受 - 无质量过滤，只要测试成功就接受"""
    if not test_result:
        return False
    
    # 只要任意一个测试成功就接受该流
    speed_success = test_result.get("speed_success", False)
    ffmpeg_success = test_result.get("ffmpeg_success", False)
    response_ok = test_result.get("response_time", 99999) < 99999  # 响应时间测试成功
    
    # 接受条件：速度测试成功 或 FFmpeg测试成功 或 响应时间测试成功
    return speed_success or ffmpeg_success or response_ok

def test_single_stream(stream_info):
    """单流测试 - 无质量过滤"""
    try:
        program_name = stream_info["program_name"]
        stream_url = stream_info["stream_url"]
        
        # 并行执行测试
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_response = executor.submit(test_stream_response_time, stream_url)
            future_speed = executor.submit(test_connection_speed, stream_url)
            future_ffmpeg = executor.submit(analyze_stream_with_ffmpeg, stream_url)
            
            try:
                response_time = future_response.result(timeout=TEST_TIMEOUT)
                speed_result = future_speed.result(timeout=SPEED_TEST_DURATION + 2)
                ffmpeg_result = future_ffmpeg.result(timeout=12)
            except:
                return None
        
        # 合并测试结果
        result = {
            "program_name": program_name,
            "stream_url": stream_url,
            "response_time": response_time,
            "actual_speed_kbps": speed_result.get("actual_speed_kbps", 0),
            "speed_success": speed_result.get("success", False),
            "ffmpeg_success": ffmpeg_result.get("ffmpeg_success", False),
            "has_video": ffmpeg_result.get("has_video", False),
            "codec": ffmpeg_result.get("codec", "unknown"),
            "protocol": ffmpeg_result.get("protocol", "UNKNOWN"),
            "analysis_time": ffmpeg_result.get("analysis_time", 0)
        }
        
        # 判断流是否可接受 - 无质量过滤
        if is_stream_acceptable(result):
            # 根据测试结果显示不同状态
            if result["ffmpeg_success"] and result["speed_success"]:
                status = "🎯"  # 优秀
            elif result["ffmpeg_success"]:
                status = "✅"  # FFmpeg通过
            elif result["speed_success"]:
                status = "📊"  # 速度通过
            else:
                status = "⏱️"   # 仅响应时间通过
            
            # 显示详细信息
            speed_info = f"速度:{result['actual_speed_kbps']:.0f}kbps" if result["speed_success"] else "速度:---"
            ffmpeg_info = "FFmpeg:✓" if result["ffmpeg_success"] else "FFmpeg:✗"
            response_info = f"响应:{response_time:.0f}ms" if response_time < 99999 else "响应:---"
            
            print(f"  {status} {program_name} ({speed_info} {response_info} {ffmpeg_info})")
            return result
        else:
            print(f"  ✗ {program_name} (所有测试均失败)")
            return None
        
    except Exception as e:
        return None

def test_all_streams(streams):
    """流测试 - 无质量过滤"""
    if not streams:
        return []
    
    print(f"开始测试 {len(streams)} 个流...")
    print("测试标准: 无质量过滤，只要任一测试成功即接受\n")
    
    tested_streams = []
    failed_count = 0
    passed_count = 0
    ffmpeg_success_count = 0
    speed_success_count = 0
    response_success_count = 0
    
    # 使用tqdm显示进度条
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_stream = {
            executor.submit(test_single_stream, stream): stream 
            for stream in streams
        }
        
        with tqdm(total=len(streams), desc="测试进度", unit="流") as pbar:
            for future in as_completed(future_to_stream):
                try:
                    result = future.result(timeout=20)
                    if result:
                        tested_streams.append(result)
                        passed_count += 1
                        if result.get("ffmpeg_success"):
                            ffmpeg_success_count += 1
                        if result.get("speed_success"):
                            speed_success_count += 1
                        if result.get("response_time", 99999) < 99999:
                            response_success_count += 1
                    else:
                        failed_count += 1
                except Exception:
                    failed_count += 1
                    future.cancel()
                finally:
                    pbar.update(1)
    
    print(f"\n✓ 测试完成!")
    print(f"  - 总测试: {len(streams)}")
    print(f"  - 测试通过: {passed_count}")
    print(f"  - FFmpeg验证通过: {ffmpeg_success_count}")
    print(f"  - 速度测试通过: {speed_success_count}")
    print(f"  - 响应测试通过: {response_success_count}")
    print(f"  - 测试失败: {failed_count}")
    
    if passed_count > 0:
        # 计算统计数据
        avg_speed = sum(s.get("actual_speed_kbps", 0) for s in tested_streams) / passed_count
        avg_response = sum(s.get("response_time", 0) for s in tested_streams if s.get("response_time", 99999) < 99999) / max(1, response_success_count)
        
        print(f"  - 平均速度: {avg_speed:.0f}kbps")
        if response_success_count > 0:
            print(f"  - 平均响应: {avg_response:.0f}ms")
    
    print(f"  - 总成功率: {passed_count/len(streams)*100:.1f}%\n")
    
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
        # 按综合质量排序：优先FFmpeg验证通过的，然后按速度
        def stream_score(stream):
            score = stream.get("actual_speed_kbps", 0)
            if stream.get("ffmpeg_success"):
                score += 10000  # FFmpeg验证通过的优先
            return score
        
        sorted_streams = sorted(channel_streams, key=stream_score, reverse=True)
        
        # 限制每个频道的接口数量
        if FINAL_SOURCES_PER_CHANNEL > 0:
            selected = sorted_streams[:FINAL_SOURCES_PER_CHANNEL]
        else:
            selected = sorted_streams
            
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

# ============================ 输出函数 ============================

def save_to_txt(streams):
    """保存为TXT格式"""
    print(f"保存到: {OUTPUT_TXT}")
    
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
            "speed": stream.get("actual_speed_kbps", 0),
            "ffmpeg_verified": stream.get("ffmpeg_success", False)
        })
    
    try:
        with open(OUTPUT_TXT, 'w', encoding='utf-8') as f:
            total_channels = 0
            total_streams = 0
            verified_streams = 0
            
            # 按模板顺序写入
            for channel_name in template_channels:
                if channel_name in channels_dict:
                    # 按质量排序
                    streams_list = sorted(channels_dict[channel_name], 
                                        key=lambda x: (x["ffmpeg_verified"], x["speed"]), 
                                        reverse=True)
                    
                    for stream_info in streams_list:
                        f.write(f"{channel_name},{stream_info['url']}\n")
                        total_streams += 1
                        if stream_info["ffmpeg_verified"]:
                            verified_streams += 1
                    
                    total_channels += 1
        
        print(f"✓ TXT文件保存成功: {total_channels} 个频道, {total_streams} 个流")
        print(f"  - FFmpeg验证流: {verified_streams} 个\n")
        
    except Exception as e:
        print(f"✗ TXT文件保存失败: {e}\n")

def save_to_m3u(streams):
    """保存为M3U格式"""
    print(f"保存到: {OUTPUT_M3U}")
    
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
            "speed": stream.get("actual_speed_kbps", 0),
            "response_time": stream.get("response_time", 0),
            "ffmpeg_verified": stream.get("ffmpeg_success", False),
            "codec": stream.get("codec", "unknown")
        })
    
    try:
        with open(OUTPUT_M3U, 'w', encoding='utf-8') as f:
            f.write("#EXTM3U\n")
            f.write(f"# Generated by IPTV Processor (No Quality Filter) on {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# Total Channels: {len(channels_dict)}\n")
            f.write(f"# Total Streams: {len(streams)}\n\n")
            
            total_channels = 0
            total_streams = 0
            verified_streams = 0
            
            # 按模板顺序写入
            for channel_name in template_channels:
                if channel_name in channels_dict:
                    # 按质量排序
                    streams_list = sorted(channels_dict[channel_name], 
                                        key=lambda x: (x["ffmpeg_verified"], x["speed"]), 
                                        reverse=True)
                    
                    for stream_info in streams_list:
                        # 标记FFmpeg验证状态
                        verified_mark = "✓" if stream_info["ffmpeg_verified"] else "⚠"
                        
                        f.write(f'#EXTINF:-1 tvg-id="{channel_name}" tvg-name="{channel_name}" '
                               f'group-title="Live",{channel_name} '
                               f'[{verified_mark}] 速度:{stream_info["speed"]:.0f}kbps\n')
                        f.write(f'{stream_info["url"]}\n')
                        total_streams += 1
                        if stream_info["ffmpeg_verified"]:
                            verified_streams += 1
                    
                    total_channels += 1
            
        print(f"✓ M3U文件保存成功: {total_channels} 个频道, {total_streams} 个流")
        print(f"  - FFmpeg验证流: {verified_streams} 个\n")
            
    except Exception as e:
        print(f"✗ M3U文件保存失败: {e}\n")

# ============================ 主函数 ============================

def main():
    """主函数"""
    print("🎬 IPTV直播源处理工具 - 无质量过滤版")
    print("=" * 60)
    print(f"开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60 + "\n")
    
    start_time = time.time()
    
    try:
        # 加载配置
        global template_channels, blacklist_keywords
        template_channels = load_template_channels()
        blacklist_keywords = load_blacklist()
        
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
        
        print(f"✓ 开始测试 {len(all_streams)} 个流...\n")
        
        # 测试所有流
        tested_streams = test_all_streams(all_streams)
        
        if not tested_streams:
            print("✗ 错误: 测试后没有可用的流\n")
            return
        
        # 分组选择最佳流
        print("正在选择最佳流...")
        selected_streams = group_and_select_streams(tested_streams)
        
        # 按模板排序
        final_streams = sort_by_template(selected_streams)
        
        # 保存文件
        print("正在保存文件...")
        save_to_txt(final_streams)
        save_to_m3u(final_streams)
        
        # 计算总耗时
        end_time = time.time()
        total_time = end_time - start_time
        
        print("=" * 60)
        print("🎉 无质量过滤版处理完成!")
        print(f"⏱ 总耗时: {total_time:.2f} 秒")
        print(f"📁 输出文件: {OUTPUT_TXT}, {OUTPUT_M3U}")
        print("=" * 60 + "\n")
        
    except KeyboardInterrupt:
        print("\n\n⚠ 用户中断执行")
    except Exception as e:
        print(f"\n\n✗ 程序执行出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
