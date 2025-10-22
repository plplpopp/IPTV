#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
IPTV直播源智能处理工具
功能：多源抓取 + FFmpeg测速 + 智能排序 + 模板匹配 + 智能频道匹配
"""

import requests
import pandas as pd
import re
import os
import subprocess
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

# ============================ 配置文件 ============================

# 源配置
URLS = [
    "https://raw.githubusercontent.com/zwc456baby/iptv_alive/master/live.txt",
    "https://live.zbds.top/tv/iptv6.txt",
    "https://live.zbds.top/tv/iptv4.txt",
]

# 功能开关
ENABLE_FFMPEG = True              # FFmpeg测速开关
ENABLE_SPEED_TEST = True          # 智能测速开关  
ENABLE_RESPONSE_TEST = True       # 响应延时测试开关
ENABLE_TEMPLATE_FILTER = True     # 模板过滤开关
ENABLE_BLACKLIST_FILTER = True    # 黑名单过滤开关
ENABLE_SMART_MATCH = True         # 智能频道匹配开关

# 权重配置
SPEED_WEIGHT = 0.5                # 测速权重
RESOLUTION_WEIGHT = 0.5           # 分辨率权重
RESPONSE_WEIGHT = 0.5             # 响应时间权重

# 数量配置
MAX_SOURCES_PER_CHANNEL = 0       # 每个频道最大接口数 (0表示不限制)
FINAL_SOURCES_PER_CHANNEL = 10    # 最终保留接口数

# 文件配置
LOCAL_SOURCE_FILE = "local.txt"   # 本地源文件
TEMPLATE_FILE = "demo.txt"        # 模板频道文件
BLACKLIST_FILE = "blacklist.txt"  # 黑名单文件
OUTPUT_TXT = "iptv.txt"           # 输出文本文件
OUTPUT_M3U = "iptv.m3u"           # 输出M3U文件

# 测试配置
FFMPEG_PATH = "ffmpeg"            # FFmpeg路径
TEST_TIMEOUT = 10                 # 测试超时时间(秒)

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

# ============================ 文件处理函数 ============================

def load_local_sources():
    """加载本地源文件"""
    local_streams = []
    if os.path.exists(LOCAL_SOURCE_FILE):
        print(f"正在加载本地源: {LOCAL_SOURCE_FILE}")
        try:
            with open(LOCAL_SOURCE_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and channel_pattern.match(line):
                        match = channel_pattern.match(line)
                        local_streams.append({
                            "program_name": match.group(1).strip(),
                            "stream_url": match.group(2).strip()
                        })
            print(f"✓ 本地源加载完成: {len(local_streams)} 个频道")
        except Exception as e:
            print(f"✗ 本地源加载失败: {e}")
    else:
        print(f"ℹ 本地源文件不存在: {LOCAL_SOURCE_FILE}")
    return local_streams

def load_template_channels():
    """加载模板频道列表"""
    channels = []
    if os.path.exists(TEMPLATE_FILE):
        print(f"正在加载模板频道: {TEMPLATE_FILE}")
        try:
            with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        channels.append(line)
            print(f"✓ 模板频道加载完成: {len(channels)} 个频道")
        except Exception as e:
            print(f"✗ 模板频道加载失败: {e}")
    else:
        print(f"✗ 模板文件不存在: {TEMPLATE_FILE}")
        # 创建示例模板文件
        try:
            with open(TEMPLATE_FILE, 'w', encoding='utf-8') as f:
                f.write("# 模板频道列表\nCCTV-1\nCCTV-2\n湖南卫视\n浙江卫视\n安徽卫视\n")
            print(f"ℹ 已创建示例模板文件: {TEMPLATE_FILE}")
        except Exception as e:
            print(f"✗ 创建示例模板文件失败: {e}")
    return channels

def load_blacklist():
    """加载黑名单关键词"""
    keywords = []
    if os.path.exists(BLACKLIST_FILE):
        print(f"正在加载黑名单: {BLACKLIST_FILE}")
        try:
            with open(BLACKLIST_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        keywords.append(line.lower())
            print(f"✓ 黑名单加载完成: {len(keywords)} 个关键词")
        except Exception as e:
            print(f"✗ 黑名单加载失败: {e}")
    else:
        print(f"ℹ 黑名单文件不存在: {BLACKLIST_FILE}")
    return keywords

# ============================ 智能频道匹配函数 ============================

def normalize_channel_name(name):
    """标准化频道名称"""
    if not name:
        return ""
    
    # 转换为小写并移除空格
    normalized = name.lower().replace(' ', '')
    
    # 移除常见后缀
    suffixes = ['hd', '高清', '4k', '超清', 'fhd', 'uhd', 'live', '卫视', '电视台']
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
        if best_match and best_score > 0.6:
            mapping[actual] = best_match
            print(f"  📺 频道匹配: '{actual}' -> '{best_match}' (置信度: {best_score:.2f})")
    
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
        print("ℹ 未找到可匹配的频道")
        return streams
    
    # 应用频道映射
    matched_streams = []
    unmatched_count = 0
    
    for stream in streams:
        original_name = stream["program_name"]
        if original_name in channel_mapping:
            # 更新为标准化频道名称
            stream["program_name"] = channel_mapping[original_name]
            matched_streams.append(stream)
        else:
            unmatched_count += 1
    
    print(f"✓ 频道匹配完成: {len(matched_streams)} 个流已匹配, {unmatched_count} 个流未匹配")
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
                print(f"✗ 黑名单拦截: {url}, 关键词: {keyword}")
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
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
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

def parse_content(content):
    """解析直播源内容"""
    streams = []
    if not content:
        return streams
        
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if match := channel_pattern.match(line):
            program_name = match.group(1).strip()
            stream_url = match.group(2).strip()
            
            # 黑名单过滤
            if is_blacklisted(stream_url):
                continue
                
            streams.append({
                "program_name": program_name,
                "stream_url": stream_url
            })
    return streams

def fetch_all_online_sources():
    """获取所有在线源"""
    online_streams = []
    print("开始获取在线源...")
    for url in URLS:
        if content := fetch_streams_from_url(url):
            streams = parse_content(content)
            online_streams.extend(streams)
            print(f"  ✓ 从 {url} 获取 {len(streams)} 个流")
        else:
            print(f"  ✗ 跳过: {url}")
    return online_streams

# ============================ 测试函数 ============================

def test_stream_response_time(stream_url):
    """测试流响应时间"""
    if not ENABLE_RESPONSE_TEST:
        return 0
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Range': 'bytes=0-1'  # 只请求少量数据
        }
        start_time = time.time()
        response = requests.head(stream_url, timeout=TEST_TIMEOUT, 
                               allow_redirects=True, headers=headers)
        if response.status_code in [200, 206]:
            return (time.time() - start_time) * 1000  # 转换为毫秒
    except Exception as e:
        pass
    return 9999  # 超时返回大值

def test_stream_with_ffmpeg(stream_url):
    """使用FFmpeg测试流信息"""
    if not ENABLE_FFMPEG or not ENABLE_SPEED_TEST:
        return {"speed": 0, "resolution": 0}
    
    try:
        # 检查ffmpeg是否可用
        subprocess.run([FFMPEG_PATH, '-version'], capture_output=True, timeout=5)
    except:
        print(f"✗ FFmpeg不可用，跳过测速")
        return {"speed": 0, "resolution": 0}
    
    try:
        cmd = [
            FFMPEG_PATH, '-i', stream_url, 
            '-t', '3', '-f', 'null', '-',  # 只测试3秒
            '-hide_banner', '-loglevel', 'error'
        ]
        
        start_time = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=TEST_TIMEOUT)
        duration = time.time() - start_time
        
        # 解析输出获取分辨率
        resolution = 0
        output = result.stderr
        if 'Video:' in output:
            if match := re.search(r'(\d+)x(\d+)', output):
                w, h = int(match.group(1)), int(match.group(2))
                resolution = w * h
        
        speed_score = 1.0 / duration if duration > 0 else 0
        return {
            "speed": speed_score,
            "resolution": resolution
        }
    except subprocess.TimeoutExpired:
        return {"speed": 0, "resolution": 0}
    except Exception as e:
        return {"speed": 0, "resolution": 0}

def calculate_stream_score(stream_data):
    """计算流综合得分"""
    try:
        speed = stream_data.get("speed", 0)
        resolution = stream_data.get("resolution", 0)
        response_time = stream_data.get("response_time", 9999)
        
        # 归一化处理
        norm_speed = min(speed / 5.0, 1.0) if speed > 0 else 0
        norm_resolution = min(resolution / (1920*1080), 1.0) if resolution > 0 else 0
        norm_response = max(0, 1 - (response_time / 3000))  # 3秒内为有效
        
        score = (norm_speed * SPEED_WEIGHT + 
                 norm_resolution * RESOLUTION_WEIGHT + 
                 norm_response * RESPONSE_WEIGHT)
        
        return round(score, 4)
    except Exception as e:
        print(f"计算得分错误: {e}")
        return 0

def test_single_stream(stream_info):
    """测试单个流"""
    try:
        program_name = stream_info["program_name"]
        stream_url = stream_info["stream_url"]
        
        # 测试响应时间
        response_time = test_stream_response_time(stream_url)
        
        # 测试流质量
        ffmpeg_result = test_stream_with_ffmpeg(stream_url)
        
        result = {
            "program_name": program_name,
            "stream_url": stream_url,
            "response_time": response_time,
            "speed": ffmpeg_result["speed"],
            "resolution": ffmpeg_result["resolution"],
            "score": 0
        }
        
        result["score"] = calculate_stream_score(result)
        return result
    except Exception as e:
        print(f"测试流失败: {stream_info.get('program_name', 'Unknown')}, 错误: {e}")
        return None

def test_all_streams(streams):
    """测试所有流"""
    if not streams:
        return []
    
    print(f"开始测试 {len(streams)} 个流...")
    
    tested_streams = []
    
    # 使用tqdm显示进度条
    with ThreadPoolExecutor(max_workers=5) as executor:  # 减少线程数避免资源竞争
        # 提交所有任务
        future_to_stream = {}
        for stream in streams:
            future = executor.submit(test_single_stream, stream)
            future_to_stream[future] = stream
        
        # 使用tqdm创建进度条
        with tqdm(total=len(streams), desc="测试进度", unit="流", 
                 bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]") as pbar:
            for future in as_completed(future_to_stream):
                try:
                    result = future.result()
                    if result:  # 只添加有效结果
                        tested_streams.append(result)
                except Exception as e:
                    # 测试失败的流跳过
                    pass
                finally:
                    pbar.update(1)
    
    print(f"✓ 测试完成! 有效流: {len(tested_streams)}/{len(streams)}")
    return tested_streams

# ============================ 数据处理函数 ============================

def filter_by_template(streams):
    """根据模板过滤频道"""
    if not ENABLE_TEMPLATE_FILTER or not template_channels:
        print("ℹ 模板过滤已禁用或模板为空")
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
    
    print(f"✓ 模板过滤: {len(filtered_streams)}/{len(streams)} 个流")
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
    
    print(f"分组完成: {len(channels_dict)} 个频道")
    
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
        
        # 显示每个频道的接口数量
        print(f"  {channel_name}: {len(selected)} 个接口")
    
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
        print("✗ 没有数据可保存")
        return
    
    # 按频道分组
    channels_dict = {}
    for stream in streams:
        name = stream["program_name"]
        if name not in channels_dict:
            channels_dict[name] = []
        channels_dict[name].append({
            "url": stream["stream_url"],
            "score": stream.get("score", 0)
        })
    
    try:
        with open(OUTPUT_TXT, 'w', encoding='utf-8') as f:
            # 按模板顺序写入
            total_channels = 0
            total_streams = 0
            
            for channel_name in template_channels:
                if channel_name in channels_dict:
                    # 按得分排序并限制数量
                    streams_list = sorted(channels_dict[channel_name], 
                                        key=lambda x: x["score"], reverse=True)
                    if FINAL_SOURCES_PER_CHANNEL > 0:
                        streams_list = streams_list[:FINAL_SOURCES_PER_CHANNEL]
                    
                    for stream_info in streams_list:
                        f.write(f"{channel_name},{stream_info['url']}\n")
                    
                    total_channels += 1
                    total_streams += len(streams_list)
            
            print(f"✓ TXT文件保存成功: {total_channels} 个频道, {total_streams} 个流")
            
    except Exception as e:
        print(f"✗ TXT文件保存失败: {e}")

def save_to_m3u(streams):
    """保存为M3U格式"""
    print(f"保存到: {OUTPUT_M3U}")
    
    if not streams:
        print("✗ 没有数据可保存")
        return
    
    # 按频道分组
    channels_dict = {}
    for stream in streams:
        name = stream["program_name"]
        if name not in channels_dict:
            channels_dict[name] = []
        channels_dict[name].append({
            "url": stream["stream_url"],
            "score": stream.get("score", 0)
        })
    
    try:
        with open(OUTPUT_M3U, 'w', encoding='utf-8') as f:
            f.write("#EXTM3U\n")
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
                        f.write(f'#EXTINF:-1 tvg-name="{channel_name}",{channel_name}\n')
                        f.write(f'{stream_info["url"]}\n')
                    
                    total_channels += 1
                    total_streams += len(streams_list)
            
            print(f"✓ M3U文件保存成功: {total_channels} 个频道, {total_streams} 个流")
            
    except Exception as e:
        print(f"✗ M3U文件保存失败: {e}")

def display_channel_stats(streams):
    """显示频道统计信息"""
    if not streams:
        return
    
    channels_dict = {}
    for stream in streams:
        name = stream["program_name"]
        if name not in channels_dict:
            channels_dict[name] = 0
        channels_dict[name] += 1
    
    print("\n" + "="*50)
    print("频道接口数量统计:")
    print("="*50)
    
    # 按模板顺序显示
    for channel_name in template_channels:
        if channel_name in channels_dict:
            count = channels_dict[channel_name]
            # 限制最终显示数量
            final_count = min(count, FINAL_SOURCES_PER_CHANNEL) if FINAL_SOURCES_PER_CHANNEL > 0 else count
            print(f"  {channel_name}: {final_count} 个接口 (测试通过: {count} 个)")
    
    total_channels = sum(1 for channel in template_channels if channel in channels_dict)
    total_streams = sum(min(channels_dict[channel], FINAL_SOURCES_PER_CHANNEL) 
                       if FINAL_SOURCES_PER_CHANNEL > 0 else channels_dict[channel]
                       for channel in template_channels if channel in channels_dict)
    
    print("="*50)
    print(f"总计: {total_channels} 个频道, {total_streams} 个流")
    print("="*50)

# ============================ 主函数 ============================

def main():
    """主函数"""
    print("🎬 IPTV直播源智能处理工具")
    print("=" * 50)
    
    # 加载配置
    global template_channels, blacklist_keywords
    template_channels = load_template_channels()
    blacklist_keywords = load_blacklist()
    
    if ENABLE_TEMPLATE_FILTER and not template_channels:
        print("✗ 错误: 模板过滤已启用但模板为空")
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
        print("✗ 错误: 没有找到任何直播源")
        return
    
    print(f"✓ 总共收集到: {len(all_streams)} 个流")
    
    # 模板过滤（包含智能匹配）
    if ENABLE_TEMPLATE_FILTER:
        all_streams = filter_by_template(all_streams)
    
    if not all_streams:
        print("✗ 错误: 过滤后没有可用的流")
        return
    
    # 测试所有流
    tested_streams = test_all_streams(all_streams)
    
    if not tested_streams:
        print("✗ 错误: 测试后没有可用的流")
        return
    
    # 分组选择最佳流
    print("\n正在选择最佳流...")
    selected_streams = group_and_select_streams(tested_streams)
    
    # 按模板排序
    final_streams = sort_by_template(selected_streams)
    
    # 显示统计信息
    display_channel_stats(final_streams)
    
    # 保存文件
    print("\n正在保存文件...")
    save_to_txt(final_streams)
    save_to_m3u(final_streams)
    
    print("=" * 50)
    print("🎉 处理完成!")
    print(f"📁 输出文件: {OUTPUT_TXT}, {OUTPUT_M3U}")

if __name__ == "__main__":
    main()
