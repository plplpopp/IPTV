#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
IPTV直播源整理工具
"""

import requests
import pandas as pd
import re
import os
import subprocess
from urllib.parse import urlparse
from collections import defaultdict
import concurrent.futures
import time
from tqdm import tqdm

# ====================== 配置文件 ======================
# 网络源URL列表
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

# 本地文件配置
LOCAL_SOURCE = "local.txt"        # 本地直播源文件
BLACKLIST_FILE = "blacklist.txt"  # 黑名单文件(每行一个关键词)
TEMPLATE_FILE = "demo.txt"        # 频道模板文件

# 输出文件配置
OUTPUT_TXT = "iptv.txt"           # 输出文本文件
OUTPUT_M3U = "iptv.m3u"           # 输出M3U文件

# 处理参数配置
MAX_SOURCES_PER_CHANNEL = 8       # 每个频道最多保留源数量
SPEED_TEST_TIMEOUT = 8            # FFmpeg测速超时时间(秒)
MAX_WORKERS = 10                  # 最大并发测速线程数

# 需要移除的词语和字符
UNWANTED_WORDS = ['综合', '高清', '超清', '4K', '4k', 'HD', 'hd', '标清', '直播', '频道']
UNWANTED_CHARS = ['·', '|', '_', '（', '）', '【', '】']

# ====================== 工具函数 ======================

def check_ffmpeg():
    """检查FFmpeg是否可用"""
    try:
        subprocess.run(["ffmpeg", "-version"], 
                      stdout=subprocess.PIPE, 
                      stderr=subprocess.PIPE, 
                      check=True)
        return True
    except:
        return False

def speed_test(url):
    """
    使用FFmpeg测试流媒体响应速度
    返回: {"url": url, "time": 毫秒, "status": "success|failed|timeout|error"}
    """
    try:
        start_time = time.time()
        cmd = [
            "ffmpeg",
            "-i", url,
            "-t", str(SPEED_TEST_TIMEOUT),
            "-f", "null",
            "-",
            "-v", "quiet",
            "-stats"
        ]
        process = subprocess.run(cmd, 
                                stdout=subprocess.PIPE, 
                                stderr=subprocess.PIPE, 
                                timeout=SPEED_TEST_TIMEOUT)
        end_time = time.time()
        
        response_time = (end_time - start_time) * 1000
        
        if process.returncode == 0:
            return {"url": url, "time": response_time, "status": "success"}
        else:
            return {"url": url, "time": response_time, "status": "failed"}
    except subprocess.TimeoutExpired:
        return {"url": url, "time": SPEED_TEST_TIMEOUT * 1000, "status": "timeout"}
    except:
        return {"url": url, "time": SPEED_TEST_TIMEOUT * 1000, "status": "error"}

def speed_test_batch(urls):
    """批量测速"""
    results = []
    with tqdm(total=len(urls), desc="测速进度", unit="源") as pbar:
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_url = {executor.submit(speed_test, url): url for url in urls}
            for future in concurrent.futures.as_completed(future_to_url):
                results.append(future.result())
                pbar.update(1)
    return results

def standardize_channel_name(name):
    """标准化频道名称(CCTV-1格式)"""
    if not name:
        return name
    
    # 处理央视
    if 'CCTV' in name or 'cctv' in name:
        name = re.sub(r'CCTV[\s\-_]?(\d+)', lambda m: f"CCTV-{m.group(1)}", name, flags=re.IGNORECASE)
        name = re.sub(r'央视(\d+)', lambda m: f"CCTV-{m.group(1)}", name)
    # 处理卫视
    elif '卫视' in name:
        name = re.sub(r'([^\s]+)卫视', r'\1卫视', name)
    
    return name

def clean_channel_name(name):
    """清洗频道名称(移除不需要的词语和字符)"""
    if not name:
        return name
    
    name = standardize_channel_name(name)
    
    # 移除不需要的词语
    for word in UNWANTED_WORDS:
        name = name.replace(word, '')
    
    # 移除不需要的字符
    for char in UNWANTED_CHARS:
        name = name.replace(char, '')
    
    # 清理括号和多余符号
    name = re.sub(r'\([^)]*\)', '', name)
    name = re.sub(r'[\s\-]+', '-', name)
    name = re.sub(r'\s+', ' ', name).strip()
    
    return name

# ====================== 文件处理函数 ======================

def load_blacklist():
    """加载黑名单关键词(每行一个)"""
    blacklist = []
    if os.path.exists(BLACKLIST_FILE):
        with open(BLACKLIST_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    blacklist.append(line.lower())
    return blacklist

def load_template():
    """加载频道模板(保持原始顺序)"""
    template = []
    current_genre = None
    
    if os.path.exists(TEMPLATE_FILE):
        with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("#genre#"):
                    current_genre = line.replace("#genre#", "").strip()
                    template.append(("#genre#", current_genre))
                elif current_genre is not None:
                    cleaned_name = clean_channel_name(line)
                    if cleaned_name:
                        template.append(("channel", cleaned_name, current_genre))
    return template

def is_blocked(url, blacklist):
    """检查URL是否在黑名单中"""
    if not blacklist:
        return False
    
    parsed = urlparse(url)
    netloc = parsed.netloc.split(':')[0].lower()
    
    for keyword in blacklist:
        if keyword in netloc or keyword in url.lower():
            return True
    return False

def fetch_streams_from_url(url):
    """从URL获取直播源内容"""
    try:
        response = requests.get(url, timeout=10)
        response.encoding = 'utf-8'
        if response.status_code == 200:
            return response.text
        print(f"\n从 {url} 获取数据失败，状态码: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"\n请求 {url} 时发生错误: {e}")
    return None

def load_local_source():
    """加载本地直播源文件"""
    if os.path.exists(LOCAL_SOURCE):
        with open(LOCAL_SOURCE, 'r', encoding='utf-8') as f:
            return f.read()
    return None

def fetch_all_streams(blacklist):
    """从所有来源获取直播源"""
    all_streams = []
    
    # 优先加载本地源
    if local_content := load_local_source():
        all_streams.append(local_content)
    
    # 加载网络源
    with tqdm(URLS, desc="抓取源进度", unit="源") as pbar:
        for url in pbar:
            pbar.set_postfix_str(url.split('/')[-1])
            if is_blocked(url, blacklist):
                pbar.write(f"跳过黑名单中的源: {url}")
                continue
                
            if content := fetch_streams_from_url(url):
                all_streams.append(content)
            else:
                pbar.write(f"跳过来源: {url}")
    return "\n".join(all_streams)

# ====================== 解析函数 ======================

def parse_m3u(content, blacklist):
    """解析M3U格式内容"""
    streams = defaultdict(list)
    current_program = None
    current_genre = None
    
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("#EXTINF"):
            if match := re.search(r'tvg-name="([^"]+)"', line):
                current_program = clean_channel_name(match.group(1))
            if match := re.search(r'group-title="([^"]+)"', line):
                current_genre = match.group(1).strip()
        elif line.startswith("#genre#"):
            current_genre = line.replace("#genre#", "").strip()
        elif line.startswith("http"):
            if current_program and not is_blocked(line, blacklist):
                streams[current_program].append({
                    "url": line.strip(),
                    "genre": current_genre if current_genre else "未分类"
                })
                current_program = None
    return streams

def parse_txt(content, blacklist):
    """解析TXT格式内容"""
    streams = defaultdict(list)
    current_genre = None
    
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
            
        if line.startswith("#genre#"):
            current_genre = line.replace("#genre#", "").strip()
        elif match := re.match(r"(.+?),\s*(http.+)", line):
            url = match.group(2).strip()
            if not is_blocked(url, blacklist):
                cleaned_name = clean_channel_name(match.group(1))
                if cleaned_name:
                    streams[cleaned_name].append({
                        "url": url,
                        "genre": current_genre if current_genre else "未分类"
                    })
    return streams

# ====================== 整理函数 ======================

def organize_streams(content, blacklist, template):
    """
    按照模板整理直播源
    1. 严格按模板顺序
    2. 每个频道最多保留MAX_SOURCES_PER_CHANNEL个源
    3. 使用FFmpeg测速选择最优源
    """
    # 根据内容类型选择解析器
    parser = parse_m3u if content.startswith("#EXTM3U") else parse_txt
    all_streams = parser(content, blacklist)
    
    # 检查FFmpeg是否可用
    use_speed_test = check_ffmpeg()
    if not use_speed_test:
        print("警告: FFmpeg未安装，将无法进行测速")
    else:
        print("开始测速分析...")
    
    # 按照模板顺序整理结果
    result = []
    current_genre = None
    
    # 计算需要测速的频道数量
    total_channels = len([item for item in template if item[0] == "channel"])
    processed_channels = 0
    
    with tqdm(total=total_channels, desc="整理频道进度", unit="频道") as pbar:
        for item in template:
            if item[0] == "#genre#":
                current_genre = item[1]
                result.append(("#genre#", current_genre))
            else:
                channel_name = item[1]
                genre = item[2]
                sources = all_streams.get(channel_name, [])
                
                # 测速并排序
                if use_speed_test and len(sources) > 1:
                    pbar.set_postfix_str(f"{channel_name} ({len(sources)}源)")
                    urls = [s["url"] for s in sources]
                    speed_results = speed_test_batch(urls)
                    
                    # 合并测速结果
                    for i, res in enumerate(speed_results):
                        sources[i]["speed_test"] = res
                    
                    # 按响应时间排序(升序)
                    sources.sort(key=lambda x: x.get("speed_test", {}).get("time", float('inf')))
                    
                    # 只保留成功的源
                    sources = [s for s in sources if s.get("speed_test", {}).get("status") == "success"]
                
                # 限制源数量
                sources = sources[:MAX_SOURCES_PER_CHANNEL]
                
                # 保留频道即使没有源
                result.append(("channel", channel_name, genre, sources))
                processed_channels += 1
                pbar.update(1)
    
    return result

# ====================== 输出函数 ======================

def save_to_txt(organized_data):
    """保存为TXT格式"""
    with open(OUTPUT_TXT, 'w', encoding='utf-8') as f:
        for item in organized_data:
            if item[0] == "#genre#":
                f.write(f"\n#genre#{item[1]}\n")
            else:
                channel_name, genre, sources = item[1], item[2], item[3]
                if sources:
                    for source in sources:
                        speed_info = ""
                        if "speed_test" in source:
                            speed_info = f" #响应时间:{int(source['speed_test']['time'])}ms"
                        f.write(f"{channel_name},{source['url']}{speed_info}\n")
                else:
                    f.write(f"{channel_name},\n")
    print(f"\n文本文件已保存: {os.path.abspath(OUTPUT_TXT)}")

def save_to_m3u(organized_data):
    """保存为M3U格式"""
    with open(OUTPUT_M3U, 'w', encoding='utf-8') as f:
        f.write("#EXTM3U\n")
        for item in organized_data:
            if item[0] == "channel":
                channel_name, genre, sources = item[1], item[2], item[3]
                for source in sources:
                    speed_info = ""
                    if "speed_test" in source:
                        speed_info = f" #响应时间:{int(source['speed_test']['time'])}ms"
                    f.write(f'#EXTINF:-1 tvg-name="{channel_name}" group-title="{genre}",{channel_name}{speed_info}\n{source["url"]}\n')
    print(f"M3U文件已保存: {os.path.abspath(OUTPUT_M3U)}")

# ====================== 主程序 ======================

def main():
    print("=== IPTV直播源整理工具 ===")
    print(f"版本: 2023-10-28")
    print(f"配置: 每个频道最多{MAX_SOURCES_PER_CHANNEL}个源, 测速超时{SPEED_TEST_TIMEOUT}秒")
    
    # 加载配置
    print("\n[1/4] 加载配置...")
    blacklist = load_blacklist()
    if blacklist:
        print(f"加载黑名单关键词: {', '.join(blacklist)}")
    
    template = load_template()
    if not template:
        print("错误: 未找到模板文件 demo.txt")
        exit(1)
    print(f"加载频道模板: {len([x for x in template if x[0] == 'channel'])}个频道")
    
    # 获取直播源
    print("\n[2/4] 抓取直播源...")
    if content := fetch_all_streams(blacklist):
        print(f"\n获取到 {len(content.splitlines())} 行数据")
    else:
        print("错误: 未能获取有效数据")
        exit(1)
    
    # 整理数据
    print("\n[3/4] 整理数据...")
    organized = organize_streams(content, blacklist, template)
    
    # 保存结果
    print("\n[4/4] 保存结果...")
    save_to_txt(organized)
    save_to_m3u(organized)
    
    print("\n=== 处理完成 ===")

if __name__ == "__main__":
    main()
