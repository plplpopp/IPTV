import sys
import time
import socket
import requests
import json
import re
import os
import threading
import ipaddress
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('iptv_system.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

class MassIPTVScanner:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Connection': 'keep-alive'
        })
        self.timeout = 2
        self.found_servers = []
        self.lock = threading.Lock()
        self.scan_stats = {
            'ips_scanned': 0,
            'ports_tested': 0,
            'servers_found': 0,
            'start_time': time.time()
        }
        
        # 生成所有端口 0-9999
        self.all_ports = list(range(10000))
        
        # 常用端口优先
        self.priority_ports = [80, 8080, 8000, 8001, 8002, 8081, 8082, 8090, 8888, 9000, 
                              7080, 8088, 8008, 8010, 8089, 8091, 8099, 8880, 9001, 82, 81, 84, 85]
        
        # 扩展JSON路径
        self.json_paths = [
            "/iptv/live/1000.json?key=txiptv",
            "/iptv/live/1000.json",
            "/live/1000.json",
            "/tv/1000.json",
            "/iptv/live.json",
            "/api/live",
            "/live.json",
            "/iptv/api/channels",
            "/api/channels",
            "/channels.json",
            "/tv/live.json",
            "/stream/live.json",
            "/hlslive.json",
            "/m3u/live.json",
            "/live/playlist.json",
            "/api/playlist",
            "/playlist.json"
        ]

    def generate_all_ips_for_prefix(self, ip_prefix):
        """生成指定IP前缀的所有可能IP（后两段0-255）"""
        ip_list = []
        base_parts = ip_prefix.split('.')
        
        if len(base_parts) != 2:
            logging.error(f"❌ Invalid IP prefix: {ip_prefix}")
            return ip_list
        
        # 生成所有可能的IP
        for third_octet in range(256):
            for fourth_octet in range(256):
                ip = f"{base_parts[0]}.{base_parts[1]}.{third_octet}.{fourth_octet}"
                ip_list.append(ip)
        
        logging.info(f"🎯 Generated {len(ip_list)} IPs for prefix {ip_prefix}")
        return ip_list

    def get_all_ip_prefixes(self):
        """获取所有要扫描的IP前缀"""
        all_prefixes = []
        
        # 中国IP段范围
        china_ip_ranges = [
            # 1.0.0.0 - 126.255.255.255 (除127.0.0.0/8)
            # 但实际主要使用以下段
            
            # A类地址段
            "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.", "10.", "11.", "12.", "13.", "14.", 
            
            # 主要电信段
            "58.16", "58.17", "58.18", "58.19", "58.20", "58.21", "58.22", "58.23", "58.24", "58.25",
            "60.0", "60.1", "60.2", "60.3", "60.4", "60.5", "60.6", "60.7", "60.8", "60.9",
            "61.128", "61.129", "61.130", "61.131", "61.132", "61.133", "61.134", "61.135",
            "113.0", "113.1", "113.2", "113.3", "113.4", "113.5", "113.6", "113.7", "113.8", "113.9",
            "114.80", "114.81", "114.82", "114.83", "114.84", "114.85", "114.86", "114.87",
            "115.48", "115.49", "115.50", "115.51", "115.52", "115.53", "115.54", "115.55",
            "116.1", "116.2", "116.3", "116.4", "116.5", "116.6", "116.7", "116.8", "116.9",
            "117.8", "117.9", "117.10", "117.11", "117.12", "117.13", "117.14", "117.15",
            "118.74", "118.75", "118.76", "118.77", "118.78", "118.79", "118.80", "118.81",
            "119.0", "119.1", "119.2", "119.3", "119.4", "119.5", "119.6", "119.7", "119.8",
            
            # 联通段
            "60.16", "60.17", "60.18", "60.19", "60.20", "60.21", "60.22", "60.23", "60.24", "60.25",
            "61.160", "61.161", "61.162", "61.163", "61.164", "61.165", "61.166", "61.167",
            "111.0", "111.1", "111.2", "111.3", "111.4", "111.5", "111.6", "111.7", "111.8",
            "112.0", "112.1", "112.2", "112.3", "112.4", "112.5", "112.6", "112.7", "112.8",
            "114.224", "114.225", "114.226", "114.227", "114.228", "114.229", "114.230", "114.231",
            
            # 移动段
            "120.192", "120.193", "120.194", "120.195", "120.196", "120.197", "120.198", "120.199",
            "121.0", "121.1", "121.2", "121.3", "121.4", "121.5", "121.6", "121.7", "121.8",
            "122.0", "122.1", "122.2", "122.3", "122.4", "122.5", "122.6", "122.7", "122.8",
            
            # 其他常见段
            "123.132", "124.112", "125.64", "126.128"
        ]
        
        # 去重
        all_prefixes = list(set(all_prefixes + china_ip_ranges))
        
        logging.info(f"🎯 Total {len(all_prefixes)} IP prefixes to scan")
        return all_prefixes

    def ultra_fast_port_check(self, ip, port):
        """超快速端口检查"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.8)  # 非常短的超时
            result = sock.connect_ex((ip, port))
            sock.close()
            return result == 0
        except:
            return False

    def quick_iptv_check(self, ip, port):
        """快速IPTV服务检查"""
        base_url = f"http://{ip}:{port}"
        
        # 只测试最可能成功的几个路径
        test_paths = [
            "/iptv/live/1000.json?key=txiptv",
            "/iptv/live/1000.json",
            "/live/1000.json"
        ]
        
        for json_path in test_paths:
            try:
                url = urljoin(base_url, json_path)
                response = self.session.get(url, timeout=1.5)
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        # 基本验证是否是IPTV数据
                        if isinstance(data, dict) and 'data' in data:
                            if isinstance(data['data'], list) and len(data['data']) > 0:
                                return True, url, len(data['data'])
                        elif isinstance(data, list) and len(data) > 0:
                            # 检查第一个元素是否有频道信息
                            if len(data) > 0 and isinstance(data[0], dict):
                                if any(key in data[0] for key in ['name', 'title', 'url']):
                                    return True, url, len(data)
                    except:
                        continue
            except:
                continue
                
        return False, None, 0

    def scan_single_ip_all_ports(self, ip):
        """扫描单个IP的所有端口(0-9999)"""
        found_ports = []
        
        # 先扫描优先级端口
        for port in self.priority_ports:
            if self.ultra_fast_port_check(ip, port):
                is_iptv, url, channel_count = self.quick_iptv_check(ip, port)
                if is_iptv:
                    with self.lock:
                        self.found_servers.append({
                            'ip': ip,
                            'port': port,
                            'url': url,
                            'channel_count': channel_count,
                            'server_url': f"http://{ip}:{port}",
                            'scan_time': time.strftime('%Y-%m-%d %H:%M:%S')
                        })
                        self.scan_stats['servers_found'] += 1
                    found_ports.append(port)
                    logging.info(f"🎯 FOUND: {ip}:{port} - {channel_count} channels")
        
        # 如果找到了服务器，就不继续扫描其他端口了
        if found_ports:
            return found_ports
        
        # 如果没有找到，随机扫描一些其他端口
        other_ports = [p for p in self.all_ports if p not in self.priority_ports]
        sample_ports = random.sample(other_ports, min(50, len(other_ports)))  # 随机采样50个端口
        
        for port in sample_ports:
            if self.ultra_fast_port_check(ip, port):
                is_iptv, url, channel_count = self.quick_iptv_check(ip, port)
                if is_iptv:
                    with self.lock:
                        self.found_servers.append({
                            'ip': ip,
                            'port': port,
                            'url': url,
                            'channel_count': channel_count,
                            'server_url': f"http://{ip}:{port}",
                            'scan_time': time.strftime('%Y-%m-%d %H:%M:%S')
                        })
                        self.scan_stats['servers_found'] += 1
                    found_ports.append(port)
                    logging.info(f"🎯 FOUND: {ip}:{port} - {channel_count} channels")
                    break  # 找到一个就停止
        
        with self.lock:
            self.scan_stats['ips_scanned'] += 1
            self.scan_stats['ports_tested'] += len(self.priority_ports) + len(sample_ports)
        
        return found_ports

    def scan_ip_prefix_massively(self, ip_prefix, sample_rate=0.1):
        """大规模扫描IP前缀"""
        logging.info(f"🔍 MASS SCAN: {ip_prefix}.*.* (0-9999 ports)")
        all_ips = self.generate_all_ips_for_prefix(ip_prefix)
        
        # 采样一部分IP进行扫描（避免数量太大）
        if sample_rate < 1.0:
            sample_size = int(len(all_ips) * sample_rate)
            scan_ips = random.sample(all_ips, sample_size)
            logging.info(f"📊 Sampling {sample_size} IPs from {len(all_ips)} (rate: {sample_rate})")
        else:
            scan_ips = all_ips
            logging.info(f"📊 Scanning ALL {len(all_ips)} IPs")
        
        found_count = 0
        
        # 分批处理
        batch_size = 200
        for i in range(0, len(scan_ips), batch_size):
            batch_ips = scan_ips[i:i + batch_size]
            batch_found = 0
            
            with ThreadPoolExecutor(max_workers=20) as executor:
                future_to_ip = {executor.submit(self.scan_single_ip_all_ports, ip): ip for ip in batch_ips}
                
                for future in as_completed(future_to_ip):
                    ip = future_to_ip[future]
                    try:
                        ports = future.result()
                        if ports:
                            batch_found += 1
                    except Exception as e:
                        pass
            
            found_count += batch_found
            
            # 进度显示
            progress = min(i + batch_size, len(scan_ips))
            elapsed = time.time() - self.scan_stats['start_time']
            rate = self.scan_stats['ips_scanned'] / elapsed if elapsed > 0 else 0
            
            logging.info(f"📊 {ip_prefix}: {progress}/{len(scan_ips)} - "
                        f"Found: {found_count} - "
                        f"Rate: {rate:.1f} IP/s - "
                        f"Total: {self.scan_stats['servers_found']} servers")
            
            # 每批之间短暂延迟
            time.sleep(0.5)
        
        return found_count

    def run_complete_scan(self, max_prefixes=5, sample_rate=0.05):
        """运行完整扫描"""
        all_prefixes = self.get_all_ip_prefixes()
        scan_prefixes = all_prefixes[:max_prefixes]
        
        total_found = 0
        
        logging.info("🚀 STARTING MASSIVE IPTV SCAN")
        logging.info("=" * 70)
        logging.info(f"📡 Scanning {max_prefixes} IP prefixes")
        logging.info(f"🎯 Port range: 0-9999")
        logging.info(f"📊 IP sample rate: {sample_rate}")
        logging.info("=" * 70)
        
        for i, prefix in enumerate(scan_prefixes):
            logging.info(f"\n🔍 [{i+1}/{len(scan_prefixes)}] Scanning prefix: {prefix}")
            
            prefix_found = self.scan_ip_prefix_massively(prefix, sample_rate)
            total_found += prefix_found
            
            logging.info(f"✅ Prefix {prefix} completed: {prefix_found} servers found")
            
            # 实时保存结果
            self.save_progress()
            
            # 如果找到很多服务器，可以继续下一个
            if prefix_found > 0:
                logging.info(f"🎯 Good results from {prefix}, continuing...")
            else:
                logging.info(f"⏩ No servers in {prefix}, moving to next...")
            
            # 前缀间延迟
            time.sleep(1)
        
        return total_found

    def save_progress(self, filename="all_servers_complete.txt"):
        """实时保存扫描进度"""
        if not self.found_servers:
            return
        
        try:
            # 按端口排序
            sorted_servers = sorted(self.found_servers, key=lambda x: (x['ip'], x['port']))
            
            with open(filename, "w", encoding="utf-8") as f:
                f.write("# COMPLETE IPTV SERVER LIST\n")
                f.write(f"# Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"# Total Servers: {len(self.found_servers)}\n")
                f.write(f"# IPs Scanned: {self.scan_stats['ips_scanned']}\n")
                f.write(f"# Ports Tested: {self.scan_stats['ports_tested']}\n")
                f.write("# Format: IP:Port,ServerURL,ChannelCount,ScanTime\n")
                f.write("# \n")
                
                for server in sorted_servers:
                    f.write(f"{server['ip']}:{server['port']},{server['server_url']},{server['channel_count']},{server['scan_time']}\n")
            
            # 同时保存简化的服务器列表
            with open("discovered_servers.txt", "w", encoding="utf-8") as f:
                f.write("# IPTV Servers for Collection\n")
                for server in sorted_servers:
                    f.write(f"{server['server_url']}\n")
                    
            logging.info(f"💾 Progress saved: {len(self.found_servers)} servers")
            
        except Exception as e:
            logging.error(f"❌ Error saving progress: {e}")

    def show_final_stats(self):
        """显示最终统计"""
        elapsed = time.time() - self.scan_stats['start_time']
        
        logging.info("\n" + "=" * 70)
        logging.info("📊 MASS SCAN COMPLETED")
        logging.info("=" * 70)
        logging.info(f"⏱️  Total time: {elapsed:.2f} seconds")
        logging.info(f"🔍 IPs scanned: {self.scan_stats['ips_scanned']}")
        logging.info(f"🎯 Ports tested: {self.scan_stats['ports_tested']}")
        logging.info(f"🚀 Servers found: {self.scan_stats['servers_found']}")
        
        if self.scan_stats['ips_scanned'] > 0:
            success_rate = (self.scan_stats['servers_found'] / self.scan_stats['ips_scanned']) * 100
            logging.info(f"📈 Success rate: {success_rate:.4f}%")
        
        if self.found_servers:
            # 按频道数量排序显示最佳服务器
            best_servers = sorted(self.found_servers, key=lambda x: x['channel_count'], reverse=True)[:15]
            logging.info("\n🏆 Top 15 Servers (by channel count):")
            for i, server in enumerate(best_servers, 1):
                logging.info(f"   {i:2d}. {server['ip']}:{server['port']} - {server['channel_count']} channels")
            
            # 端口统计
            port_stats = {}
            for server in self.found_servers:
                port = server['port']
                port_stats[port] = port_stats.get(port, 0) + 1
            
            common_ports = sorted(port_stats.items(), key=lambda x: x[1], reverse=True)[:10]
            logging.info("\n🔢 Most common ports:")
            for port, count in common_ports:
                logging.info(f"   Port {port}: {count} servers")
        
        logging.info("=" * 70)

def run_mass_scan():
    """运行大规模扫描"""
    scanner = MassIPTVScanner()
    
    try:
        # 运行完整扫描
        total_found = scanner.run_complete_scan(
            max_prefixes=3,      # 扫描3个IP前缀
            sample_rate=0.02     # 2%的IP采样率
        )
        
        # 显示最终统计
        scanner.show_final_stats()
        
        # 最终保存
        scanner.save_progress()
        
        return len(scanner.found_servers)
        
    except KeyboardInterrupt:
        logging.info("\n⏹️ Scan interrupted by user")
        scanner.show_final_stats()
        scanner.save_progress()
        return len(scanner.found_servers)
    except Exception as e:
        logging.error(f"❌ Scan failed: {e}")
        scanner.show_final_stats()
        scanner.save_progress()
        return len(scanner.found_servers)

# 主函数
def main():
    """主函数"""
    if not sys.stdin.isatty():
        logging.info("🤖 Starting MASSIVE IPTV Scanner")
        server_count = run_mass_scan()
        logging.info(f"🎯 Scan completed with {server_count} servers found")
    else:
        print("\n🎯 MASSIVE IPTV SCANNER")
        print("🔍 Scans ALL IPs and ALL ports (0-9999)")
        print("=" * 50)
        print("This will scan:")
        print("  • Multiple IP prefixes")
        print("  • All ports 0-9999") 
        print("  • Save ALL valid servers")
        print("=" * 50)
        
        confirm = input("Start massive scan? (y/n): ").strip().lower()
        if confirm == 'y':
            server_count = run_mass_scan()
            print(f"\n✅ Scan completed! Found {server_count} servers.")
        else:
            print("Scan cancelled.")

if __name__ == "__main__":
    main()
