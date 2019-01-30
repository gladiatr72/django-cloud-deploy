import copy
import os.path
import random
import re
import string
import time
from typing import Any, Callable, Dict, List, Optional
import webbrowser

from django_cloud_deploy import workflow
from django_cloud_deploy.cli import io
from django_cloud_deploy.cloudlib import auth
from django_cloud_deploy.cloudlib import billing
from django_cloud_deploy.cloudlib import project


def _ask_prompt(question: str,
                console: io.IO,
                validate: Optional[Callable[[str], None]] = None,
                default: Optional[str] = None) -> str:
    """Used to ask for a single string value.

    Args:
        question: Question shown to the user on the console.
        console: Object to use for user I/O.
        validate: Function used to check if value provided is valid. It should
            raise a ValueError if the the value fials to validate.
        default: Default value if user provides no value. (Presses enter)

    Returns:
        The value entered by the user.
    """
    validate = validate or (lambda x: None)
    while True:
        answer = console.ask(question)
        if default and answer is '':
            answer = default
        try:
            validate(answer)
            break
        except ValueError as e:
            console.error(e)

    return answer


def _multiple_choice_prompt(question: str,
                            options: List[str],
                            console: io.IO,
                            default: Optional[str] = None):
    """Used to prompt user to choose from a list of values.

    Args:
        question: Question shown to the user on the console. Should have
            a {} to insert a list of enumerated options.
        options: Possible values user should choose from.
        console: Object to use for user I/O.
        default: Default value if user provides no value. (Presses enter)

    Returns:
        The choice entered by the user.
    """
    options_formatted = [
        '{}. {}'.format(str(i), opt) for i, opt in enumerate(options, 1)
    ]
    options = '\n'.join(options_formatted)
    answer = console.ask(question.format(options))

    while True:
        try:
            _multiple_choice_validate(answer, default, len(options))
            break
        except ValueError as e:
            console.error(e)
            answer = console.ask(question)

    return answer


def _multiple_choice_validate(s: str, default: Optional[str], len_options: int):
    """Validates the option chosen is valid.

    Args:
        s: Value to validate.
        default: Default value if user provides no value. (Presses enter)
        len_options: Amount of possible options for the user.

    Raises:
        ValueError: If the answer is not valid.
    """
    if default is not None and s == '':
        return

    if not str.isnumeric(s):
        raise ValueError('Please enter a numeric value')

    if 1 <= int(s) <= (len_options + 1):
        return
    else:
        raise ValueError('Value is not in range')


def _binary_prompt(question: str, console: io.IO,
                   default: Optional[str] = None):
    """Used to prompt user to choose from a yes or no question.

    Args:
        question: Question shown to the user on the console.
        console: Object to use for user I/O.
        default: Default value if user provides no value. (Presses enter)
    """

    while True:
        try:
            answer = console.ask(question)
            if default and answer is '':
                answer = default
                _binary_validate(answer)
            break
        except ValueError as e:
            console.error(e)

    return answer


def _binary_validate(s: str):
    """Ensures value is yes or no.

    Args:
        s: Value to validate.
    """
    if s.lower() not in ['y', 'n']:
        raise ValueError('Please respond using "y" or "n"')

    return


def _password_prompt(question: str, console: io.IO) -> str:
    """Used to prompt user to choose a password field.

    Args:
        console: Object to use for user I/O.
        question: Question shown to the user on the console.
    """
    console.tell(question)
    while True:
        password1 = console.getpass('Password: ')
        try:
            _password_validate(password1)
        except ValueError as e:
            console.error(e)
            continue
        password2 = console.getpass('Password (again): ')
        if password1 != password2:
            console.error('Passwords do not match, please try again')
            continue
        return password1


def _password_validate(s):
    """Validates that a string is a valid password.

    Args:
        s: The string to validate.

    Raises:
        ValueError: if the input string is not valid.
    """
    if len(s) < 5:
        raise ValueError('Passwords must be at least 6 characters long')
    allowed_characters = frozenset(string.ascii_letters + string.digits +
                                   string.punctuation)
    if frozenset(s).issuperset(allowed_characters):
        raise ValueError('Invalid character in password: '
                         'use letters, numbers and punctuation')

    return


class TemplatePrompt(object):
    """Used as a base template for all Parameter Prompts interacting with user.

    They must have a prompt method that calls one of the _x_prompt functions.
    They must own only one parameter.
    They must have a validate function.
    They will validate the value if passed in as a flag.
    """

    # Parameter must be set for dictionary key
    PARAMETER = None

    def prompt(self, console: io.IO, step: str,
               args: Dict[str, Any]) -> Dict[str, Any]:
        """Handles the business logic and calls the prompts.

        Args:
            console: Object to use for user I/O.
            step: Message to present to user regarding what step they are on.
            args: Dictionary holding prompts answered by user and set up
                arguments.

        Returns: A Copy of args + the new parameter collected.
        """
        pass

    def _validate(self, val: str):
        """Checks if the string is valid. Throws a ValueError if not valid."""
        pass

    def _is_valid_passed_arg(self, console: io.IO, step: str,
                             value: Optional[str],
                             validate: Callable[[str], None]) -> bool:
        """Used to validate if the user passed in a parameter as a flag.

        All s that retrieve a parameter should call this function first.
        It requires all s to have implemented validate. The code also
        will process a passed in paramater as a step. This is used to have a
        hard coded amount of steps that is easy to manage.

        Returns:
            A boolean indicating if the passed in argument is valid.
        """
        if value is None:
            return False

        try:
            validate(value)
        except ValueError as e:
            console.error(e)
            return False

        msg = '{} {}: {}'.format(step, self.PARAMETER, value)
        console.tell(msg)
        return True


class StringTemplatePrompt(TemplatePrompt):
    """Template for a simple string Prompt ."""

    PARAMETER = ''
    PARAMETER_PRETTY = ''
    DEFAULT_VALUE = ''
    BASE_MESSAGE = '{} Enter a value for {} or leave blank to use'
    DEFAUlT_MESSAGE = '[{}]: '

    def prompt(self, console: io.IO, step: str,
               args: Dict[str, Any]) -> Dict[str, Any]:
        new_args = copy.deepcopy(args)
        if self._is_valid_passed_arg(console, step,
                                     args.get(self.PARAMETER, None),
                                     self._validate):
            return new_args

        base_message = self.BASE_MESSAGE.format(step, self.PARAMETER_PRETTY)
        default_message = self.DEFAUlT_MESSAGE.format(self.DEFAULT_VALUE)
        msg = '\n'.join([base_message, default_message])
        answer = _ask_prompt(
            msg, console, self._validate, default=self.DEFAULT_VALUE)
        new_args[self.PARAMETER] = answer
        return new_args


class GoogleProjectName(TemplatePrompt):

    PARAMETER = 'project_name'

    def __init__(self, project_client: project.ProjectClient):
        self.project_client = project_client

    def _validate(self, project_id: str,
                  project_creation_mode: workflow.ProjectCreationMode
                 ) -> Callable[[str], None]:
        """Returns the method that validates the string.

        Args:
            project_id: Used to retrieve name when project already exists.
            project_creation_mode: Used to check if project already exists.
        """

        def helper(s: str):
            if not (4 <= len(s) <= 30):
                raise ValueError(
                    ('Invalid Google Cloud Platform project name "{}": '
                     'must be between 4 and 30 characters').format(s))

            if self._is_new_project(project_creation_mode):
                return

            if project_id is None:
                raise ValueError('Project Id must be set')

            project_name = self.project_client.get_project(project_id)['name']
            if project_name != s:
                raise ValueError('Wrong project name given for project id.')

        return helper

    def _handle_new_project(self, console: io.IO, step: str, args: [str, Any]):
        default_answer = 'Django Project'
        msg_base = ('{} Enter a Google Cloud Platform project name, or leave '
                    'blank to use').format(step)
        msg_default = '[{}]: '.format(default_answer)
        msg = '\n'.join([msg_base, msg_default])
        project_id = args.get('project_id', None)
        project_creation_mode = args.get('project_creation_mode', None)
        return _ask_prompt(
            msg,
            console,
            self._validate(project_id, project_creation_mode),
            default=default_answer)

    def _is_new_project(
            self, project_creation_mode: workflow.ProjectCreationMode) -> bool:
        must_exist = workflow.ProjectCreationMode.MUST_EXIST
        return project_creation_mode != must_exist

    def _handle_existing_project(self, console: io.IO, step: str,
                                 args: Dict[str, Any]) -> str:
        assert 'project_id' in args, 'project_id must be set'
        project_id = args['project_id']
        project_name = self.project_client.get_project(project_id)['name']
        message = '{} {}: {}'.format(step, self.PARAMETER, project_name)
        console.tell(message)
        return project_name

    def prompt(self, console: io.IO, step: str,
               args: Dict[str, Any]) -> Dict[str, Any]:
        new_args = copy.deepcopy(args)

        project_id = args.get('project_id', None)
        project_creation_mode = args.get('project_creation_mode', None)
        if self._is_valid_passed_arg(
                console, step, args.get(self.PARAMETER, None),
                self._validate(project_id, project_creation_mode)):
            return new_args

        project_creation_mode = args.get('project_creation_mode', None)
        if self._is_new_project(project_creation_mode):
            new_args[self.PARAMETER] = self._handle_new_project(
                console, step, args)
        else:
            new_args[self.PARAMETER] = self._handle_existing_project(
                console, step, args)

        return new_args


class GoogleNewProjectId(TemplatePrompt):
    """Handles Project ID for new projects."""

    PARAMETER = 'project_id'

    def _validate(self, s: str):
        """Validates that a string is a valid project id.

        Args:
            s: The string to validate.

        Raises:
            ValueError: if the input string is not valid.
        """
        if not re.match(r'[a-z][a-z0-9\-]{5,29}', s):
            raise ValueError(('Invalid Google Cloud Platform Project ID "{}": '
                              'must be between 6 and 30 characters and contain '
                              'lowercase letters, digits or hyphens').format(s))

    def _generate_default_project_id(self, project_name=None):
        default_project_id = (project_name or 'django').lower()
        default_project_id = default_project_id.replace(' ', '-')
        if default_project_id[0] not in string.ascii_lowercase:
            default_project_id = 'django-' + default_project_id
        default_project_id = re.sub(r'[^a-z0-9\-]', '', default_project_id)

        return '{0}-{1}'.format(default_project_id[0:30 - 6 - 1],
                                random.randint(100000, 1000000))

    def prompt(self, console: io.IO, step: str,
               args: Dict[str, Any]) -> Dict[str, Any]:
        new_args = copy.deepcopy(args)
        if self._is_valid_passed_arg(console, step,
                                     args.get(self.PARAMETER, None),
                                     self._validate):
            return new_args

        project_name = args.get('project_name', None)
        default_answer = self._generate_default_project_id(project_name)
        msg_base = ('{} Enter a Google Cloud Platform Project ID, '
                    'or leave blank to use').format(step)
        msg_default = '[{}]: '.format(default_answer)
        msg = '\n'.join([msg_base, msg_default])
        answer = _ask_prompt(
            msg, console, self._validate, default=default_answer)
        new_args[self.PARAMETER] = answer
        return new_args


class GoogleProjectId(TemplatePrompt):
    """ that handles fork between Existing and New Projects."""

    PARAMETER = 'project_id'

    def __init__(self, project_client: project.ProjectClient):
        self.project_client = project_client

    def prompt(self, console: io.IO, step: str,
               args: Dict[str, Any]) -> Dict[str, Any]:
        prompter = GoogleNewProjectId()

        if args.get('use_existing_project', False):
            prompter = GoogleExistingProjectId(self.project_client)

        return prompter.prompt(console, step, args)


class GoogleExistingProjectId(TemplatePrompt):
    """Handles Project ID for existing projects."""

    PARAMETER = 'project_id'

    def __init__(self, project_client: project.ProjectClient):
        self.project_client = project_client

    def prompt(self, console: io.IO, step: str,
               args: Dict[str, Any]) -> Dict[str, Any]:
        """Prompt the user to a Google Cloud Platform project id.

        If the user supplies the project_id as a flag we want to validate that
        it exists. We tell the user to supply a new one if it does not.

        """

        new_args = copy.deepcopy(args)
        if self._is_valid_passed_arg(console, step,
                                     args.get(self.PARAMETER, None),
                                     self._validate):
            return new_args

        msg = ('{} Enter the <b>existing<b> Google Cloud Platform Project ID '
               'to use.').format(step)
        answer = _ask_prompt(msg, console, self._validate)
        new_args[self.PARAMETER] = answer
        return new_args

    def _validate(self, s: str):
        """Validates that a string is a valid project id.

        Args:
            s: The string to validate.

        Raises:
            ValueError: if the input string is not valid.
        """

        if not re.match(r'[a-z][a-z0-9\-]{5,29}', s):
            raise ValueError(('Invalid Google Cloud Platform Project ID "{}": '
                              'must be between 6 and 30 characters and contain '
                              'lowercase letters, digits or hyphens').format(s))

        if not self.project_client.project_exists(s):
            raise ValueError('Project {} does not exist'.format(s))


class CredentialsPrompt(TemplatePrompt):

    PARAMETER = 'credentials'

    def __init__(self, auth_client: auth.AuthClient):
        self.auth_client = auth_client

    def prompt(self, console: io.IO, step: str,
               args: Dict[str, Any]) -> Dict[str, Any]:
        """Prompt the user for access to the Google credentials.

        Returns:
            The user's credentials.
        """
        new_args = copy.deepcopy(args)
        if self._is_valid_passed_arg(console, step,
                                     args.get(self.PARAMETER, None),
                                     self._validate):
            return new_args

        console.tell(
            ('{} In order to deploy your application, you must allow Django '
             'Deploy to access your Google account.').format(step))
        create_new_credentials = True
        active_account = self.auth_client.get_active_account()

        msg = ('You have logged in with account [{}]. Do you want to '
               'use it? [Y/n]: ').format(active_account)
        use_active_credentials = _binary_prompt(msg, console, default='Y')

        if active_account:  # The user has already logged in before
            create_new_credentials = use_active_credentials.lower() == 'n'

        if create_new_credentials:
            creds = self.auth_client.create_default_credentials()
        else:
            creds = self.auth_client.get_default_credentials()

        new_args[self.PARAMETER] = creds
        return new_args


class BillingPrompt(TemplatePrompt):
    """Allow the user to select a billing account to use for deployment."""

    PARAMETER = 'billing_account_name'

    def __init__(self, billing_client: billing.BillingClient = None):
        self.billing_client = billing_client

    def _get_new_billing_account(
            self, console,
            existing_billing_accounts: List[Dict[str, Any]]) -> str:
        """Ask the user to create a new billing account and return name of it.

        Args:
            existing_billing_accounts: User's billing accounts before creation
                of new accounts.

        Returns:
            Name of the user's newly created billing account.
        """
        webbrowser.open('https://console.cloud.google.com/billing/create')
        existing_billing_account_names = [
            account['name'] for account in existing_billing_accounts
        ]
        console.tell('Waiting for billing account to be created.')
        while True:
            billing_accounts = self.billing_client.list_billing_accounts(
                only_open_accounts=True)
            if len(existing_billing_accounts) != len(billing_accounts):
                billing_account_names = [
                    account['name'] for account in billing_accounts
                ]
                diff = list(
                    set(billing_account_names) -
                    set(existing_billing_account_names))
                return diff[0]
            time.sleep(2)

    def _does_project_exist(
            self, project_creation_mode: Optional[workflow.ProjectCreationMode]
    ) -> bool:
        must_exist = workflow.ProjectCreationMode.MUST_EXIST
        return project_creation_mode == must_exist

    def _has_existing_billing_account(self, console: io.IO, step: str,
                                      args: Dict[str, Any]) -> (Optional[str]):
        assert 'project_id' in args, 'project_id must be set'
        project_id = args['project_id']
        billing_account = (self.billing_client.get_billing_account(project_id))
        if not billing_account.get('billingEnabled', False):
            return None

        msg = ('{} Billing is already enabled on this project.'.format(step))
        console.tell(msg)
        return billing_account.get('billingAccountName')

    def _handle_existing_billing_accounts(self, console, billing_accounts):
        question = ('You have the following existing billing accounts:\n{}\n'
                    'Please enter your numeric choice or press [Enter] to '
                    'create a new billing account: ')

        options = [info['displayName'] for info in billing_accounts]
        new_billing_account = ''

        answer = _multiple_choice_prompt(
            question, options, console, default=new_billing_account)

        if answer == new_billing_account:
            return self._get_new_billing_account(console, billing_accounts)

        val = billing_accounts[int(answer) - 1]['name']
        return val

    def prompt(self, console: io.IO, step: str,
               args: Dict[str, Any]) -> Dict[str, Any]:
        """Prompt the user for a billing account to use for deployment.
        """
        new_args = copy.deepcopy(args)
        if self._is_valid_passed_arg(console, step,
                                     args.get(self.PARAMETER, None),
                                     self._validate):
            return new_args

        project_creation_mode = args.get('project_creation_mode', None)
        if self._does_project_exist(project_creation_mode):
            billing_account = self._has_existing_billing_account(
                console, step, args)
            if billing_account is not None:
                new_args[self.PARAMETER] = billing_account
                return new_args

        billing_accounts = self.billing_client.list_billing_accounts(
            only_open_accounts=True)
        console.tell(
            ('{} In order to deploy your application, you must enable billing '
             'for your Google Cloud Project.').format(step))

        # If the user has existing billing accounts, we let the user pick one
        if billing_accounts:
            val = self._handle_existing_billing_accounts(
                console, billing_accounts)
            new_args[self.PARAMETER] = val
            return new_args

        # If the user does not have existing billing accounts, we direct
        # the user to create a new one.
        console.tell('You do not have existing billing accounts.')
        console.ask('Press [Enter] to create a new billing account.')
        val = self._get_new_billing_account(console, billing_accounts)
        new_args[self.PARAMETER] = val
        return new_args

    def validate(self, s):
        """Validates that a string is a valid billing account.

        Args:
            s: The string to validate.

        Raises:
            ValueError: if the input string is not valid.
        """

        billing_accounts = self.billing_client.list_billing_accounts()
        billing_account_names = [
            account['name'] for account in billing_accounts
        ]
        if s not in billing_account_names:
            raise ValueError('The provided billing account does not exist.')


class PostgresPasswordPrompt(TemplatePrompt):
    """Allow the user to enter a Django Postgres password."""

    PARAMETER = 'database_password'

    def prompt(self, console: io.IO, step: str,
               args: Dict[str, Any]) -> Dict[str, Any]:
        new_args = copy.deepcopy(args)
        if self._is_valid_passed_arg(console, step,
                                     args.get(self.PARAMETER, None),
                                     self._validate):
            return new_args

        msg = 'Enter a password for the default database user "postgres"'
        question = '{} {}'.format(step, msg)
        password = _password_prompt(question, console)
        new_args[self.PARAMETER] = password
        return new_args

    def _validate(self, s: str):
        _password_validate(s)


class DjangoFilesystemPath(TemplatePrompt):
    """Allow the user to file system path for their project."""

    PARAMETER = 'django_directory_path'

    def _ask_to_replace(self, console, directory):
        msg = (('The directory \'{}\' already exists, '
                'replace it\'s contents [y/N]: ').format(directory))
        return _ask_prompt(msg, console, default='n')

    def _ask_for_directory(self, console, step, args) -> str:
        base_msg = ('{} Enter a new directory path to store project source, '
                    'or leave blank to use').format(step)

        home_dir = os.path.expanduser('~')
        # TODO: Remove filesystem-unsafe characters. Implement a validation
        # method that checks for these.
        default_dir = os.path.join(
            home_dir,
            args.get('project_name', 'django-project').lower().replace(
                ' ', '-'))
        default_msg = '[{}]: '.format(default_dir)

        msg = '\n'.join([base_msg, default_msg])
        return _ask_prompt(msg, console, default=default_dir)

    def prompt(self, console: io.IO, step: str,
               args: Dict[str, Any]) -> Dict[str, Any]:
        """Prompt the user to enter a file system path for their project."""
        new_args = copy.deepcopy(args)
        while True:
            directory = self._ask_for_directory(console, step, args)
            if os.path.exists(directory):
                replace = self._ask_to_replace(console, directory)
                if replace == 'y':
                    break
            break

        new_args[self.PARAMETER] = directory
        return new_args

    def validate(self):
        # TODO
        return


class DjangoProjectNamePrompt(StringTemplatePrompt):
    """Allow the user to enter a Django project name."""

    PARAMETER = 'django_project_name'
    PARAMETER_PRETTY = 'Django project name'
    DEFAULT_VALUE = 'mysite'

    def _validate(self, s: str):
        """Validates that a string is a valid Django project name.

        Args:
            s: The string to validate.

        Raises:
            ValueError: if the input string is not valid.
        """
        if not s.isidentifier():
            raise ValueError(('Invalid Django project name "{}": '
                              'must be a valid Python identifier').format(s))


class DjangoAppNamePrompt(StringTemplatePrompt):
    """Allow the user to enter a Django project name."""

    PARAMETER = 'django_app_name'
    PARAMETER_PRETTY = 'Django app name'
    DEFAULT_VALUE = 'home'

    def _validate(self, s: str):
        """Validates that a string is a valid Django project name.

        Args:
            s: The string to validate.

        Raises:
            ValueError: if the input string is not valid.
        """
        if not s.isidentifier():
            raise ValueError(('Invalid Django project name "{}": '
                              'must be a valid Python identifier').format(s))


class DjangoSuperuserLoginPrompt(StringTemplatePrompt):
    """Allow the user to enter a Django superuser login."""

    PARAMETER = 'django_superuser_login'
    PARAMETER_PRETTY = 'Django superuser login name'
    DEFAULT_VALUE = 'admin'

    def _validate(self, s: str):
        """Validates that a string is a valid Django superuser login.

        Args:
            s: The string to validate.

        Raises:
            ValueError: if the input string is not valid.
        """
        if not s.isalnum():
            raise ValueError(('Invalid Django superuser login "{}": '
                              'must be a alpha numeric').format(s))


class DjangoSuperuserPasswordPrompt(TemplatePrompt):
    """Allow the user to enter a password for the Django superuser."""

    PARAMETER = 'django_superuser_password'

    def prompt(self, console: io.IO, step: str,
               args: Dict[str, Any]) -> Dict[str, Any]:
        new_args = copy.deepcopy(args)
        if self._is_valid_passed_arg(console, step,
                                     args.get(self.PARAMETER, None),
                                     self._validate):
            return new_args

        msg = 'Enter a password for the Django superuser "{}"'.format(
            args['django_superuser_login'])
        question = '{} {}'.format(step, msg)
        answer = _password_prompt(question, console)
        new_args[self.PARAMETER] = answer
        return new_args

    def _validate(self, s: str):
        return _password_validate(s)


class DjangoSuperuserEmailPrompt(StringTemplatePrompt):
    """Allow the user to enter a Django email address."""

    PARAMETER = 'django_superuser_email'
    PARAMETER_PRETTY = 'Django superuser email'
    DEFAULT_VALUE = 'test@example.com'

    def _validate(self, s: str):
        """Validates that a string is a valid Django superuser email address.

        Args:
            s: The string to validate.

        Raises:
            ValueError: if the input string is not valid.
        """
        if not re.match(r'[^@]+@[^@]+\.[^@]+', s):
            raise ValueError(('Invalid Django superuser email address "{}": '
                              'the format should be like '
                              '"test@example.com"').format(s))


class RootPrompt(object):
    """Class at the top level that instantiates all of the Prompts."""

    PROMPT_ORDER = [
        'project_id',
        'project_name',
        'billing_account_name',
        'database_password',
        'django_directory_path',
        'django_project_name',
        'django_app_name',
        'django_superuser_login',
        'django_superuser_password',
        'django_superuser_email',
    ]

    def _get_creds(self, console: io.IO, first_step: str, args: Dict[str, Any]):
        auth_client = auth.AuthClient()
        return CredentialsPrompt(auth_client).prompt(console, first_step,
                                                     args)['credentials']

    def _setup_prompts(self, creds) -> Dict[str, TemplatePrompt]:
        project_client = project.ProjectClient.from_credentials(creds)
        billing_client = billing.BillingClient.from_credentials(creds)

        return {
            'project_id': GoogleProjectId(project_client),
            'project_name': GoogleProjectName(project_client),
            'billing_account_name': BillingPrompt(billing_client),
            'database_password': PostgresPasswordPrompt(),
            'django_directory_path': DjangoFilesystemPath(),
            'django_project_name': DjangoProjectNamePrompt(),
            'django_app_name': DjangoAppNamePrompt(),
            'django_superuser_login': DjangoSuperuserLoginPrompt(),
            'django_superuser_password': DjangoSuperuserPasswordPrompt(),
            'django_superuser_email': DjangoSuperuserEmailPrompt()
        }

    def prompt(self, console: io.IO, args: Dict[str, Any]) -> Dict[str, Any]:
        new_args = copy.deepcopy(args)
        if new_args.get('use_existing_project', False):
            new_args['project_creation_mode'] = (
                workflow.ProjectCreationMode.MUST_EXIST)

        total_steps = len(self.PROMPT_ORDER) + 1
        step_template = '<b>[{}/{}]</b>'
        first_step = step_template.format(1, total_steps)

        creds = self._get_creds(console, first_step, args)
        new_args['credentials'] = creds
        required_parameters_to_prompt = self._setup_prompts(creds)
        for i, prompt in enumerate(self.PROMPT_ORDER, 2):
            step = step_template.format(i, total_steps)
            new_args = required_parameters_to_prompt[prompt].prompt(
                console, step, new_args)

        return new_args
