__author__ = 'xiayf'

config = {
    'email_type': 'basic',  # or advanced
    'cpu': {
        'interval': 1,
    },
    'mem': {
        'interval': 1,
    },
    'disk': {
        'interval': 10,
    },
    'email': {
        'interval': 300,
        'server': {
            'host': '',
            'port': 465,
            'username': '',
            'password': '',
        },
        'from': '',
        'to': [''],
    }
}