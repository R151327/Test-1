import datetime
from unittest import mock

from django.db.migrations.questioner import (
    InteractiveMigrationQuestioner, MigrationQuestioner,
)
from django.db.models import NOT_PROVIDED
from django.test import SimpleTestCase
from django.test.utils import captured_stdout, override_settings


class QuestionerTests(SimpleTestCase):
    @override_settings(
        INSTALLED_APPS=['migrations'],
        MIGRATION_MODULES={'migrations': None},
    )
    def test_ask_initial_with_disabled_migrations(self):
        questioner = MigrationQuestioner()
        self.assertIs(False, questioner.ask_initial('migrations'))

    def test_ask_not_null_alteration(self):
        questioner = MigrationQuestioner()
        self.assertIsNone(questioner.ask_not_null_alteration('field_name', 'model_name'))

    @mock.patch('builtins.input', return_value='2')
    def test_ask_not_null_alteration_not_provided(self, mock):
        questioner = InteractiveMigrationQuestioner()
        with captured_stdout():
            question = questioner.ask_not_null_alteration('field_name', 'model_name')
        self.assertEqual(question, NOT_PROVIDED)


class QuestionerHelperMethodsTests(SimpleTestCase):
    questioner = InteractiveMigrationQuestioner()

    @mock.patch('builtins.input', return_value='datetime.timedelta(days=1)')
    def test_questioner_default_timedelta(self, mock_input):
        questioner = InteractiveMigrationQuestioner()
        with captured_stdout():
            value = questioner._ask_default()
        self.assertEqual(value, datetime.timedelta(days=1))

    @mock.patch('builtins.input', return_value='')
    def test_questioner_default_no_user_entry(self, mock_input):
        with captured_stdout():
            value = self.questioner._ask_default(default='datetime.timedelta(days=1)')
        self.assertEqual(value, datetime.timedelta(days=1))

    @mock.patch('builtins.input', side_effect=['', 'exit'])
    def test_questioner_no_default_no_user_entry(self, mock_input):
        with captured_stdout() as stdout, self.assertRaises(SystemExit):
            self.questioner._ask_default()
        self.assertIn(
            "Please enter some code, or 'exit' (without quotes) to exit.",
            stdout.getvalue(),
        )

    @mock.patch('builtins.input', side_effect=['bad code', 'exit'])
    def test_questioner_no_default_bad_user_entry_code(self, mock_input):
        with captured_stdout() as stdout, self.assertRaises(SystemExit):
            self.questioner._ask_default()
        self.assertIn('Invalid input: unexpected EOF while parsing', stdout.getvalue())

    @mock.patch('builtins.input', side_effect=['', 'n'])
    def test_questioner_no_default_no_user_entry_boolean(self, mock_input):
        with captured_stdout():
            value = self.questioner._boolean_input('Proceed?')
        self.assertIs(value, False)

    @mock.patch('builtins.input', return_value='')
    def test_questioner_default_no_user_entry_boolean(self, mock_input):
        with captured_stdout():
            value = self.questioner._boolean_input('Proceed?', default=True)
        self.assertIs(value, True)

    @mock.patch('builtins.input', side_effect=[10, 'garbage', 1])
    def test_questioner_bad_user_choice(self, mock_input):
        question = 'Make a choice:'
        with captured_stdout() as stdout:
            value = self.questioner._choice_input(question, choices='abc')
        expected_msg = (
            f'{question}\n'
            f' 1) a\n'
            f' 2) b\n'
            f' 3) c\n'
        )
        self.assertIn(expected_msg, stdout.getvalue())
        self.assertEqual(value, 1)
