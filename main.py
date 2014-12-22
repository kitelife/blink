# coding: utf-8

__author__ = 'xiayf'

import multiprocessing
import time
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.header import Header

import psutil


class BeautyEye(object):

    def __init__(self, config):
        self.config = config

    def __cpu_stat(self):
        stat_interval = self.config['cpu']['interval']
        while True:
            cpu_percent = psutil.cpu_percent(1)
            print '__cpu_stat', cpu_percent, '%'
            time.sleep(stat_interval)

    def __mem_stat(self):
        stat_interval = self.config['mem']['interval']
        while True:
            mem_usage = psutil.virtual_memory()
            print '__mem_stat', mem_usage.percent, '%'
            time.sleep(stat_interval)

    def __disk_stat(self):
        stat_interval = self.config['disk']['interval']
        while True:
            for dp in psutil.disk_partitions(all=False):
                print dp.mountpoint, psutil.disk_usage(dp.mountpoint).percent, '%'
            time.sleep(stat_interval)

    def __plot_data(self):
        pass

    def __render_content(self):
        content = ''
        return content

    def __prepare_data(self):
        return ''

    def __email_it(self):
        email_content = self.__prepare_data()

        msg = MIMEText(email_content, 'html', 'utf-8')
        msg['Subject'] = Header(self.config['email']['subject'] % (datetime.strftime('%Y-%m-%d %H:%M:%S'), ), 'utf-8')
        msg['From'] = Header(self.config['email']['from'], 'utf-8')
        msg['To'] = ', '.join(self.config['email']['to'])

        try:
            email_server_info = self.config['email']['server']
            s = smtplib.SMTP(email_server_info['host'], email_server_info['port'])
            s.login(email_server_info['username'], email_server_info['password'])
            s.sendmail(self.config['email']['from'], self.config['email']['to'], msg.as_string())
            s.quit()
        except Exception as e:
            print e
            return False
        return True

    def blink(self):
        process_record = []
        for m in [self.__cpu_stat, self.__mem_stat, self.__disk_stat]:
            p = multiprocessing.Process(target=m)
            p.start()
            process_record.append(p)
        for p in process_record:
            p.join()


def main():
    config = {
        'cpu': {
            'interval': 1,
        },
        'mem': {
            'interval': 1,
        },
        'disk': {
            'interval': 5,
        },
        'email': {
            'server': {
                'host': '',
                'port': '',
                'username': '',
                'password': '',
            },
            'subject': '服务器监控数据汇总 - %s',
            'from': '',
            'to': [],
        }
    }
    be = BeautyEye(config)
    be.blink()


if __name__ == '__main__':
    main()