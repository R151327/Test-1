from django.db.backends.mysql.client import DatabaseClient
from django.test import SimpleTestCase


class MySqlDbshellCommandTestCase(SimpleTestCase):

    def test_fails_with_keyerror_on_incomplete_config(self):
        with self.assertRaises(KeyError):
            self.get_command_line_arguments({})

    def test_basic_params_specified_in_settings(self):
        self.assertEqual(
            ['mysql', '--user=someuser', '--password=somepassword',
             '--host=somehost', '--port=444', 'somedbname'],
            self.get_command_line_arguments({
                'NAME': 'somedbname',
                'USER': 'someuser',
                'PASSWORD': 'somepassword',
                'HOST': 'somehost',
                'PORT': 444,
                'OPTIONS': {},
            }))

    def test_options_override_settings_proper_values(self):
        settings_port = 444
        options_port = 555
        self.assertNotEqual(settings_port, options_port, 'test pre-req')
        self.assertEqual(
            ['mysql', '--user=optionuser', '--password=optionpassword',
             '--host=optionhost', '--port={}'.format(options_port), 'optiondbname'],
            self.get_command_line_arguments({
                'NAME': 'settingdbname',
                'USER': 'settinguser',
                'PASSWORD': 'settingpassword',
                'HOST': 'settinghost',
                'PORT': settings_port,
                'OPTIONS': {
                    'db': 'optiondbname',
                    'user': 'optionuser',
                    'passwd': 'optionpassword',
                    'host': 'optionhost',
                    'port': options_port,
                },
            }))

    def test_options_password(self):
        self.assertEqual(
            [
                'mysql', '--user=someuser', '--password=optionpassword',
                '--host=somehost', '--port=444', 'somedbname',
            ],
            self.get_command_line_arguments({
                'NAME': 'somedbname',
                'USER': 'someuser',
                'PASSWORD': 'settingpassword',
                'HOST': 'somehost',
                'PORT': 444,
                'OPTIONS': {'password': 'optionpassword'},
            }),
        )

    def test_options_charset(self):
        self.assertEqual(
            [
                'mysql', '--user=someuser', '--password=somepassword',
                '--host=somehost', '--port=444',
                '--default-character-set=utf8', 'somedbname',
            ],
            self.get_command_line_arguments({
                'NAME': 'somedbname',
                'USER': 'someuser',
                'PASSWORD': 'somepassword',
                'HOST': 'somehost',
                'PORT': 444,
                'OPTIONS': {'charset': 'utf8'},
            }),
        )

    def test_can_connect_using_sockets(self):
        self.assertEqual(
            ['mysql', '--user=someuser', '--password=somepassword',
             '--socket=/path/to/mysql.socket.file', 'somedbname'],
            self.get_command_line_arguments({
                'NAME': 'somedbname',
                'USER': 'someuser',
                'PASSWORD': 'somepassword',
                'HOST': '/path/to/mysql.socket.file',
                'PORT': None,
                'OPTIONS': {},
            }))

    def test_ssl_certificate_is_added(self):
        self.assertEqual(
            ['mysql', '--user=someuser', '--password=somepassword',
             '--host=somehost', '--port=444', '--ssl-ca=sslca',
             '--ssl-cert=sslcert', '--ssl-key=sslkey', 'somedbname'],
            self.get_command_line_arguments({
                'NAME': 'somedbname',
                'USER': 'someuser',
                'PASSWORD': 'somepassword',
                'HOST': 'somehost',
                'PORT': 444,
                'OPTIONS': {
                    'ssl': {
                        'ca': 'sslca',
                        'cert': 'sslcert',
                        'key': 'sslkey',
                    },
                },
            }))

    def test_parameters(self):
        self.assertEqual(
            ['mysql', 'somedbname', '--help'],
            self.get_command_line_arguments(
                {
                    'NAME': 'somedbname',
                    'USER': None,
                    'PASSWORD': None,
                    'HOST': None,
                    'PORT': None,
                    'OPTIONS': {},
                },
                ['--help'],
            ),
        )

    def get_command_line_arguments(self, connection_settings, parameters=None):
        if parameters is None:
            parameters = []
        return DatabaseClient.settings_to_cmd_args(connection_settings, parameters)
