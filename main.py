# coding: utf-8

__author__ = 'xiayf'

import time
import functools
import smtplib
import sqlite3
import multiprocessing
import subprocess
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import COMMASPACE
from email.header import Header
from email.mime.image import MIMEImage
from collections import OrderedDict

from conf import config

import psutil
from jinja2 import Template

if config['email_type'] == 'advanced':
    import vincent
    from vincent import AxisProperties, PropertySet, ValueRef
    import pandas


class DB(object):

    def __init__(self):
        self.__conn = sqlite3.connect('data.db')
        self.__cursor = self.__conn.cursor()
        self.__prepare()

    def __prepare(self):
        table_cpu = '''CREATE TABLE IF NOT EXISTS cpu_stat (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            used_percent INTEGER NOT NULL DEFAULT -1,
            created_at TIMESTAMP
        )
        '''
        self.__cursor.execute(table_cpu)
        self.__conn.commit()

        table_mem = '''CREATE TABLE IF NOT EXISTS mem_stat (
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

    def __host_info(self):
        mem = psutil.virtual_memory()
        host_info = {
            'host_ip': self.__config['host_ip'],
            'up_time': datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M:%S"),
            'cpu_cores': psutil.cpu_count(),
            'mem_total': '{mem_total} MB'.format(mem_total=mem.total / 1024 / 1024)
        }
        return host_info

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
                  % (cpu_usage_percent, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            self.__db.execute(sql)

            cpu_stat_queue.add(cpu_usage_percent)
            if functools.reduce(self.__over_threshold, cpu_stat_queue.data, 0) == abnormal_continue_times:
                email_subject = u'服务器CPU使用率告警 - %s' % (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), )
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
                  % (mem_usage_percent, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            self.__db.execute(sql)

            mem_stat_queue.add(mem_usage_percent)
            if functools.reduce(self.__over_threshold, mem_stat_queue.data, 0) == abnormal_continue_times:
                email_subject = u'服务器内存使用率告警 - %s' % (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), )
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
                email_subject = u'服务器磁盘告警 - %s' % (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), )
                email_content_parts = []
                for mount_point, usage_percent in abnormal_mountpoint.iteritems():
                    email_content_parts.append('{mount_point}: {usage_percent}%'
                                               .format(mount_point=mount_point, usage_percent=usage_percent))
                email_content = '<br />'.join(email_content_parts)
                self.__email_alert(email_subject, email_content)

            time.sleep(stat_interval)

    def __render_content(self, template_name, data):
        data_to_render = {
            'host_info': self.__host_info(),
            'disk_info': self.__disk_info(),
            'email_type': data.pop('email_type')
        }

        if data['email_type'] == 'advanced':
            cmd_pattern = 'vega/bin/vg2png {source_file} {target_file}'

            cpu_stat = data['cpu_stat']
            cpu_stat_data = cpu_stat['data']
            cpu_data_file_name = 'cpu_stat_data.json'
            cpu_graph_file_name = cpu_stat['target_file_name']
            with open(cpu_data_file_name, 'w') as fh:
                fh.write(cpu_stat_data)
            cmd = cmd_pattern.format(source_file=cpu_data_file_name, target_file=cpu_graph_file_name)
            try:
                subprocess.check_call(cmd, shell=True)
            except subprocess.CalledProcessError as err:
                print err
                return False

            mem_stat = data['mem_stat']
            mem_stat_data = mem_stat['data']
            mem_data_file_name = 'mem_stat_data.json'
            mem_graph_file_name = mem_stat['target_file_name']
            with open(mem_data_file_name, 'w') as fh:
                fh.write(mem_stat_data)
            cmd = cmd_pattern.format(source_file=mem_data_file_name, target_file=mem_graph_file_name)
            try:
                subprocess.check_call(cmd, shell=True)
            except subprocess.CalledProcessError as err:
                print err
                return False
        else:
            data_to_render.update(data)
        with open(template_name) as fh:
            template = Template(fh.read().decode('utf-8'))
        return template.render(**data_to_render)

    @staticmethod
    def __data_preprocess(data):
        new_data = {
            'used_percent': [],
            'created_at': []
        }
        merge_count = 5
        length = len(data['created_at'])
        for index in xrange(length):
            index_quotient = index / merge_count
            index_remainder = index % merge_count
            if index_remainder == 0:
                new_data['created_at'][index_quotient] = data['created_at'][index]
            new_data['used_percent'][index_quotient] += data['used_percent'][index]
            if index_remainder == merge_count-1:
                new_data['used_percent'][index_quotient] = round(
                    float(new_data['used_percent'][index_quotient]) / merge_count,
                    2
                )
        return new_data

    def __email_it(self, subject, content, attach_files=None):
        if attach_files is None:
            attach_files = []

        msg = MIMEMultipart()
        msg['Subject'] = Header(subject, 'utf-8')
        msg['From'] = Header(self.__config['email']['from'], 'utf-8')
        msg['To'] = COMMASPACE.join(self.__config['email']['to'])
        msg.attach(MIMEText(content, 'html', 'utf-8'))

        for af in attach_files:
            img = MIMEImage(open(af['file_name'], 'rb').read())
            img.add_header('Content-ID', '<%s>' % (af['file_id'],))
            msg.attach(img)
        try:
            email_server_info = self.__config['email']['server']
            s = smtplib.SMTP_SSL(email_server_info['host'], email_server_info['port'], timeout=10)
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
        email_interval = self.__config['email']['interval']
        email_subject = '服务器监控数据'

        while True:
            time.sleep(email_interval)

            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

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
                for_delete = 'DELETE FROM %s WHERE created_at < "%s"' % (table_name, now)
                self.__db.execute(for_delete)

            # cpu
            cpu_stat_data = self.__data_preprocess(stat_data['cpu_stat'])
            # memory
            mem_stat_data = self.__data_preprocess(stat_data['mem_stat'])

            cpu_data_count = len(cpu_stat_data['created_at'])
            mem_data_count = len(mem_stat_data['created_at'])

            if self.__config['email_type'] == 'advanced':
                for index in xrange(cpu_data_count):
                    cpu_stat_data['created_at'][index] = datetime.strptime(cpu_stat_data['created_at'][index],
                                                                           '%Y-%m-%d %H:%M:%S')
                series = pandas.Series(cpu_stat_data['used_percent'], index=cpu_stat_data['created_at'])
                cpu_graph = vincent.Area(series)
                cpu_graph.axis_titles(x=u'Time', y=u'Usage (%)')
                ax = AxisProperties(labels=PropertySet(angle=ValueRef(value=150)))
                cpu_graph.axes[0].properties = ax
                cpu_graph_json = cpu_graph.to_json()

                for index in xrange(mem_data_count):
                    mem_stat_data['created_at'][index] = datetime.strptime(cpu_stat_data['created_at'][index],
                                                                           '%Y-%m-%d %H:%M:%S')
                series = pandas.Series(mem_stat_data['used_percent'], index=mem_stat_data['created_at'])
                mem_graph = vincent.Area(series)
                mem_graph.axis_titles(x=u'Time', y=u'Usage (%)')
                ax = AxisProperties(labels=PropertySet(angle=ValueRef(value=150)))
                mem_graph.axes[0].properties = ax
                mem_graph_json = mem_graph.to_json()

                email_content = self.__render_content(template_name='templates/monitor_stat.html', data={
                    'email_type': self.__config['email_type'],
                    'cpu_stat': {'data': cpu_graph_json, 'target_file_name': 'cpu_graph.png'},
                    'mem_stat': {'data': mem_graph_json, 'target_file_name': 'mem_graph.png'}
                })
                if email_content is None:
                    print u'模板渲染失败！'
                    break
                print self.__email_it(subject=email_subject, content=email_content,
                                      attach_files=[
                                          {'file_name': 'cpu_graph.png', 'file_id': 'cpu_stat'},
                                          {'file_name': 'mem_graph.png', 'file_id': 'mem_stat'}
                                      ])
            else:
                # 娶最大的5个，最小的5个
                max_n = 5

                cpu_data_tuples = [(cpu_stat_data['created_at'][index], cpu_stat_data['used_percent'][index])
                                   for index in xrange(cpu_data_count)]
                cpu_data_sorted = sorted(cpu_data_tuples, key=lambda item: item[1])
                cpu_sorted_max = []
                if cpu_data_count >= max_n:
                    cpu_sorted_max.extend(cpu_data_sorted[0-max_n:])

                mem_data_tuples = [(mem_stat_data['created_at'][index], mem_stat_data['used_percent'][index])
                                   for index in xrange(mem_data_count)]
                mem_data_sorted = sorted(mem_data_tuples, key=lambda item: item[1])
                mem_sorted_max = []
                if mem_data_count >= max_n:
                    mem_sorted_max.extend(mem_data_sorted[0-max_n:])
                email_content = self.__render_content(template_name='templates/monitor_stat.html', data={
                    'email_type': self.__config['email_type'],
                    'max_n': max_n,
                    'cpu_stat': {'max_n': cpu_sorted_max},
                    'mem_stat': {'max_n': mem_sorted_max}
                })
                if email_content is None:
                    print u'模板渲染失败！'
                    break
                print self.__email_it(subject=email_subject, content=email_content)

    def blink(self):
        process_record = []
        for m in [self.__cpu_stat, self.__mem_stat, self.__disk_stat, self.__email_summary]:
            p = multiprocessing.Process(target=m)
            p.start()
            process_record.append(p)
        for p in process_record:
            p.join()


def main():
    be = BeautyEye(config)
    be.blink()

if __name__ == '__main__':
    main()