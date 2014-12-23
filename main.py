# coding: utf-8

__author__ = 'xiayf'

import time
import functools
import smtplib
import sqlite3
import multiprocessing
from datetime import datetime
from email.mime.text import MIMEText
from email.header import Header
from collections import OrderedDict
from string import Template

import psutil
import vincent


class DB(object):

    def __init__(self):
        self.__conn = sqlite3.connect('data.db')
        self.__cursor = self.__conn.cursor()
        self.__prepare()

    def __prepare(self):
        table_cpu = '''CREATE TABLE IF NOT EXIST cpu_stat (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            used_percent INTEGER NOT NULL DEFAULT -1,
            created_at TIMESTAMP
        )
        '''
        self.__cursor.execute(table_cpu)
        self.__conn.commit()

        table_mem = '''CREATE TABLE IF NOT EXIST mem_stat (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            used_percent INTEGER NOT NULL DEFAULT -1,
            created_at TIMESTAMP
        )
        '''
        self.__cursor.execute(table_mem)
        self.__conn.commit()

    def execute(self, sql):
        self.__cursor.execute(sql)
        self.__conn.commit()

    def query(self, sql):
        for row in self.__cursor.execute(sql):
            yield row

    def close(self):
        self.__cursor.close()
        self.__conn.close()


class CircularQueue(object):

    def __init__(self, length):
        self.__length = length
        self.__pointer = 0
        self.__queue = OrderedDict()

    def add(self, value):
        self.__queue[self.__pointer] = value
        self.__pointer = (self.__pointer + 1) % self.__length

    @property
    def data(self):
        return self.__queue.values()


class BeautyEye(object):

    def __init__(self, config):
        self.__config = config
        self.__db = DB()

    @staticmethod
    def __disk_info():
        disk_info = {}
        for dp in psutil.disk_partitions(all=False):
            # print dp.mountpoint, psutil.disk_usage(dp.mountpoint).percent, '%'
            disk_info[dp.mountpoint] = psutil.disk_usage(dp.mountpoint).percent
        return disk_info

    @staticmethod
    def __host_info():
        pass

    @staticmethod
    def __over_threshold(count, value):
        return count+1 if value >= 90 else count

    def __cpu_stat(self):
        abnormal_continue_times = 3
        cpu_stat_queue = CircularQueue(abnormal_continue_times)
        stat_interval = self.__config['cpu']['interval']
        while True:
            cpu_usage_percent = psutil.cpu_percent(1)
            # print '__cpu_stat', cpu_usage_percent, '%'

            sql = 'INSERT INTO cpu_stat (used_percent, created_at) VALUES (%d, "%s")' \
                  % (cpu_usage_percent, datetime.strftime('%Y-%m-%d %H:%M:%S'))
            self.__db.execute(sql)

            cpu_stat_queue.add(cpu_usage_percent)
            if functools.reduce(self.__over_threshold, cpu_stat_queue.data, 0) == abnormal_continue_times:
                email_subject = u'服务器CPU使用率告警 - %s' % (datetime.strftime('%Y-%m-%d %H:%M:%S'), )
                email_content = u'CPU使用率已连续 {abnormal_times} 次超过 {usage_threshold}%'\
                    .format(abnormal_times=abnormal_continue_times, usage_threshold=90)
                self.__email_alert(subject=email_subject, content=email_content)

            time.sleep(stat_interval)

    def __mem_stat(self):
        abnormal_continue_times = 3
        mem_stat_queue = CircularQueue(abnormal_continue_times)
        stat_interval = self.__config['mem']['interval']
        while True:
            mem_usage = psutil.virtual_memory()
            mem_usage_percent = mem_usage.percent
            # print '__mem_stat', mem_usage_percent, '%'

            sql = 'INSERT INTO mem_stat (used_percent, created_at) VALUES (%d, "%s")' \
                  % (mem_usage_percent, datetime.strftime('%Y-%m-%d %H:%M:%S'))
            self.__db.execute(sql)

            mem_stat_queue.add(mem_usage_percent)
            if functools.reduce(self.__over_threshold, mem_stat_queue.data, 0) == abnormal_continue_times:
                email_subject = u'服务器内存使用率告警 - %s' % (datetime.strftime('%Y-%m-%d %H:%M:%S'), )
                email_content = u'内存使用率已连续 {abnormal_times} 次超过 {usage_threshold}%'\
                    .format(abnormal_times=abnormal_continue_times, usage_threshold=90)
                self.__email_alert(subject=email_subject, content=email_content)

            time.sleep(stat_interval)

    def __disk_stat(self):
        stat_interval = self.__config['disk']['interval']
        disk_threshold = 90
        while True:
            abnormal_mountpoint = {}
            for mount_point, usage_percent in self.__disk_info().iteritems():
                if usage_percent > disk_threshold:
                    abnormal_mountpoint[mount_point] = usage_percent
            if len(abnormal_mountpoint) > 0:
                email_subject = u'服务器磁盘告警 - %s' % (datetime.strftime('%Y-%m-%d %H:%M:%S'), )
                email_content_parts = []
                for mount_point, usage_percent in abnormal_mountpoint.iteritems():
                    email_content_parts.append('{mount_point}: {usage_percent}%'
                                               .format(mount_point=mount_point, usage_percent=usage_percent))
                email_content = '<br />'.join(email_content_parts)
                self.__email_alert(email_subject, email_content)

            time.sleep(stat_interval)

    @staticmethod
    def __render_content(template, data):
        with open(template) as fh:
            template = Template(str(fh.readall()))
            return template.substitute(cpu_stat_data=data['cpu_stat'], mem_stat_data=data['mem_stat'])

    def __email_it(self, subject, content):
        msg = MIMEText(content, 'html', 'utf-8')
        msg['Subject'] = Header(subject, 'utf-8')
        msg['From'] = Header(self.__config['email']['from'], 'utf-8')
        msg['To'] = ', '.join(self.__config['email']['to'])

        try:
            email_server_info = self.__config['email']['server']
            s = smtplib.SMTP(email_server_info['host'], email_server_info['port'])
            s.login(email_server_info['username'], email_server_info['password'])
            s.sendmail(self.__config['email']['from'], self.__config['email']['to'], msg.as_string())
            s.quit()
        except Exception as e:
            print e
            return False
        return True

    def __email_alert(self, subject, content):
        self.__email_it(subject=subject, content=content)

    def __email_summary(self):
        now = datetime.strftime('%Y-%m-%d %H:%M:%S')

        stat_data = {
            'cpu_stat': {
                'used_percent': [],
                'created_at': []
            },
            'mem_stat': {
                'used_percent': [],
                'created_at': []
            }
        }
        for table_name in stat_data.keys():
            for_select = 'SELECT used_percent, created_at FROM %s WHERE created_at < "%s" ORDER BY created_at' \
                         % (table_name, now)
            for row in self.__db.query(for_select):
                stat_data[table_name]['used_percent'].append(row[0])
                stat_data[table_name]['created_at'].append(row[1])
            for_delete = 'DELETE FROM %s WHERE created_at < "%s' % (table_name, now)
            self.__db.execute(for_delete)

        # cpu
        cpu_stat_data = stat_data['cpu_stat']
        cpu_graph = vincent.Area(cpu_stat_data['used_percent'])
        cpu_graph.axis_titles(x=u'时间', y=u'使用率(%)')
        cpu_graph.name(u'CPU使用率')
        cpu_graph_json = cpu_graph.to_json()

        # memory
        mem_stat_data = stat_data['mem_stat']
        mem_graph = vincent.Area(mem_stat_data['used_percent'])
        mem_graph.axis_titles(x=u'时间', y=u'使用率(%)')
        mem_graph.name(u'内存使用率')
        mem_graph_json = mem_graph.to_json()

        email_content = self.__render_content(template='templates/monitor_stat.html',
                              data={'cpu_stat': cpu_graph_json, 'mem_graph_json': mem_graph_json})
        if email_content is None:
            print u'模板渲染失败！'
            return False
        email_subject = '服务器监控数据'
        self.__email_it(subject=email_subject, content=email_content)
        return True

    def blink(self):
        process_record = []
        for m in [self.__cpu_stat, self.__mem_stat, self.__disk_stat, self.__email_summary]:
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
            'interval': 3600 * 4,
        },
        'email': {
            'interval': 3600 * 24,
            'server': {
                'host': '',
                'port': '',
                'username': '',
                'password': '',
            },
            'from': '',
            'to': [],
        }
    }
    be = BeautyEye(config)
    be.blink()

if __name__ == '__main__':
    main()