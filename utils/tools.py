from time import time
import datetime
import os
import urllib.parse
import ipaddress
from urllib.parse import urlparse
import socket
from utils.config import config, resource_path
import re
from bs4 import BeautifulSoup
from flask import render_template_string, send_file


def format_interval(t):
    """
    Formats a number of seconds as a clock time, [H:]MM:SS

    Parameters
    ----------
    t  : int or float
        Number of seconds.
    Returns
    -------
    out  : str
        [H:]MM:SS
    """
    mins, s = divmod(int(t), 60)
    h, m = divmod(mins, 60)
    if h:
        return "{0:d}:{1:02d}:{2:02d}".format(h, m, s)
    else:
        return "{0:02d}:{1:02d}".format(m, s)


def get_pbar_remaining(n=0, total=0, start_time=None):
    """
    Get the remaining time of the progress bar
    """
    try:
        elapsed = time() - start_time
        completed_tasks = n
        if completed_tasks > 0:
            avg_time_per_task = elapsed / completed_tasks
            remaining_tasks = total - completed_tasks
            remaining_time = format_interval(avg_time_per_task * remaining_tasks)
        else:
            remaining_time = "未知"
        return remaining_time
    except Exception as e:
        print(f"Error: {e}")


def update_file(final_file, old_file):
    """
    Update the file
    """
    old_file_path = resource_path(old_file, persistent=True)
    final_file_path = resource_path(final_file, persistent=True)
    if os.path.exists(old_file_path):
        os.replace(old_file_path, final_file_path)


def filter_by_date(data):
    """
    Filter by date and limit
    """
    default_recent_days = 30
    use_recent_days = config.getint("Settings", "recent_days")
    if not isinstance(use_recent_days, int) or use_recent_days <= 0:
        use_recent_days = default_recent_days
    start_date = datetime.datetime.now() - datetime.timedelta(days=use_recent_days)
    recent_data = []
    unrecent_data = []
    for (url, date, resolution), response_time in data:
        item = ((url, date, resolution), response_time)
        if date:
            date = datetime.datetime.strptime(date, "%m-%d-%Y")
            if date >= start_date:
                recent_data.append(item)
            else:
                unrecent_data.append(item)
        else:
            unrecent_data.append(item)
    recent_data_len = len(recent_data)
    if recent_data_len == 0:
        recent_data = unrecent_data
    elif recent_data_len < config.getint("Settings", "urls_limit"):
        recent_data.extend(
            unrecent_data[: config.getint("Settings", "urls_limit") - len(recent_data)]
        )
    return recent_data


def get_soup(source):
    """
    Get soup from source
    """
    source = re.sub(
        r"<!--.*?-->",
        "",
        source,
        flags=re.DOTALL,
    )
    soup = BeautifulSoup(source, "html.parser")
    return soup


def get_total_urls_from_info_list(infoList):
    """
    Get the total urls from info list
    """
    total_urls = [url for url, _, _ in infoList]
    return list(dict.fromkeys(total_urls))[: config.getint("Settings", "urls_limit")]


def get_total_urls_from_sorted_data(data):
    """
    Get the total urls with filter by date and depulicate from sorted data
    """
    total_urls = []
    if len(data) > config.getint("Settings", "urls_limit"):
        total_urls = [url for (url, _, _), _ in filter_by_date(data)]
    else:
        total_urls = [url for (url, _, _), _ in data]
    return list(dict.fromkeys(total_urls))[: config.getint("Settings", "urls_limit")]


def is_ipv6(url):
    """
    Check if the url is ipv6
    """
    try:
        host = urllib.parse.urlparse(url).hostname
        ipaddress.IPv6Address(host)
        return True
    except ValueError:
        return False


def check_url_ipv_type(url):
    """
    Check if the url is compatible with the ipv type in the config
    """
    ipv_type = config.get("Settings", "ipv_type")
    if ipv_type == "ipv4":
        return not is_ipv6(url)
    elif ipv_type == "ipv6":
        return is_ipv6(url)
    else:
        return True


def check_by_domain_blacklist(url):
    """
    Check by domain blacklist
    """
    domain_blacklist = [
        urlparse(domain).netloc if urlparse(domain).scheme else domain
        for domain in config.get("Settings", "domain_blacklist").split(",")
        if domain.strip()
    ]
    return urlparse(url).netloc not in domain_blacklist


def check_by_url_keywords_blacklist(url):
    """
    Check by URL blacklist keywords
    """
    url_keywords_blacklist = [
        keyword
        for keyword in config.get("Settings", "url_keywords_blacklist").split(",")
        if keyword.strip()
    ]
    return not any(keyword in url for keyword in url_keywords_blacklist)


def check_url_by_patterns(url):
    """
    Check the url by patterns
    """
    return (
        check_url_ipv_type(url)
        and check_by_domain_blacklist(url)
        and check_by_url_keywords_blacklist(url)
    )


def filter_urls_by_patterns(urls):
    """
    Filter urls by patterns
    """
    urls = [url for url in urls if check_url_ipv_type(url)]
    urls = [url for url in urls if check_by_domain_blacklist(url)]
    urls = [url for url in urls if check_by_url_keywords_blacklist(url)]
    return urls


def merge_objects(*objects):
    """
    Merge objects
    """

    def merge_dicts(dict1, dict2):
        for key, value in dict2.items():
            if key in dict1:
                if isinstance(dict1[key], dict) and isinstance(value, dict):
                    merge_dicts(dict1[key], value)
                elif isinstance(dict1[key], set):
                    dict1[key].update(value)
                elif isinstance(dict1[key], list):
                    dict1[key].extend(value)
                    dict1[key] = list(set(dict1[key]))  # Remove duplicates
                else:
                    dict1[key] = {dict1[key], value}
            else:
                dict1[key] = value

    merged_dict = {}
    for obj in objects:
        if not isinstance(obj, dict):
            raise TypeError("All input objects must be dictionaries")
        merge_dicts(merged_dict, obj)

    return merged_dict


def get_ip_address():
    """
    Get the IP address
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = "127.0.0.1"
    finally:
        s.close()
    return f"http://{IP}:8000"


def convert_to_m3u():
    """
    Convert result txt to m3u format
    """
    user_final_file = config.get("Settings", "final_file")
    if os.path.exists(resource_path(user_final_file)):
        with open(resource_path(user_final_file), "r", encoding="utf-8") as file:
            m3u_output = '#EXTM3U x-tvg-url="https://live.fanmingming.com/e.xml"\n'
            current_group = None
            for line in file:
                trimmed_line = line.strip()
                if trimmed_line != "":
                    if "#genre#" in trimmed_line:
                        current_group = trimmed_line.replace(",#genre#", "").strip()
                    else:
                        original_channel_name, channel_link = map(
                            str.strip, trimmed_line.split(",")
                        )
                        processed_channel_name = re.sub(
                            r"(CCTV|CETV)-(\d+).*", r"\1\2", original_channel_name
                        )
                        m3u_output += f'#EXTINF:-1 tvg-name="{processed_channel_name}" tvg-logo="https://live.fanmingming.com/tv/{processed_channel_name}.png"'
                        if current_group:
                            m3u_output += f' group-title="{current_group}"'
                        m3u_output += f",{original_channel_name}\n{channel_link}\n"
            m3u_file_path = os.path.splitext(resource_path(user_final_file))[0] + ".m3u"
            with open(m3u_file_path, "w", encoding="utf-8") as m3u_file:
                m3u_file.write(m3u_output)
            print(f"result m3u file generated at: {m3u_file_path}")


def get_result_file_content(show_result=False):
    """
    Get the content of the result file
    """
    user_final_file = config.get("Settings", "final_file")
    if config.getboolean("Settings", "open_m3u_result"):
        user_final_file = os.path.splitext(resource_path(user_final_file))[0] + ".m3u"
        if show_result == False:
            return send_file(user_final_file, as_attachment=True)
    with open(user_final_file, "r", encoding="utf-8") as file:
        content = file.read()
    return render_template_string(
        "<head><link rel='icon' href='{{ url_for('static', filename='images/favicon.ico') }}' type='image/x-icon'></head><pre>{{ content }}</pre>",
        content=content,
    )
