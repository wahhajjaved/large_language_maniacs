# Mailst: send personalized emails to your students
# Copyright (C) 2014-2020 Jesus Arias Fisteus
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see
# <http://www.gnu.org/licenses/>.
#
import re
import decimal
import smtplib
import email.encoders
import email.utils
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
import os.path
import time
import sys


class Column:
    def __init__(self, key, is_email=False, is_file=False, is_full_name=False):
        if sum(bool(x) for x in (is_email, is_file, is_full_name)) > 1:
            raise ValueError("is_full_name, is_email and is_file are " "incompatible")
        self.key = key
        self.is_email = is_email
        self.is_file = is_file
        self.is_full_name = is_full_name

    def as_dict(self, value):
        return {self.key: value}


class EmailColumn(Column):
    def __init__(self, key):
        super().__init__(key, is_email=True)


class NameColumn(Column):
    def __init__(self, key, is_full_name=False):
        super().__init__(key, is_full_name=is_full_name)

    def as_dict(self, name):
        d = {self.key: name}
        uncapitalized = NameColumn._uncapitalize(name)
        d[self.key + "_uncapitalized"] = uncapitalized
        return d

    @staticmethod
    def _uncapitalize(name):
        """From NAME SURNAME returns Name Surname"""
        names = [n.swapcase().capitalize() for n in name.split(" ")]
        for i in range(0, len(names)):
            parts = names[i].split("-")
            for j in range(1, len(parts)):
                parts[j] = parts[j].capitalize()
            names[i] = "-".join(parts)
        return " ".join(names).strip()


class FullNameColumn(NameColumn):
    def __init__(self, key):
        super().__init__(key, is_full_name=True)


class GradeColumn(Column):
    def __init__(self, key, max_grade=None, min_grade=0.0, check_max=True):
        self.max_grade = max_grade
        self.min_grade = min_grade
        self.check_max = check_max
        super().__init__(key)

    def as_dict(self, grade):
        d = {self.key: self.grade(grade)}
        if self.max_grade is not None:
            d[self.key + "_max"] = self.max_grade
        return d

    def grade(self, value):
        if value == "":
            result = None
        else:
            original_value = value
            if "," in value:
                value = re.sub(",", ".", value)
            try:
                result = decimal.Decimal(value)
            except decimal.InvalidOperation:
                msg = "Wrong decimal format: {}".format(repr(original_value))
                raise ValueError(msg)
            if (
                self.check_max
                and self.max_grade is not None
                and result > self.max_grade
            ):
                msg = "Grade {} for {} greater than its maximum value {}".format(
                    result, self.key, self.max_grade
                )
                raise ValueError(msg)
            if self.min_grade is not None and result < self.min_grade:
                msg = "Grade {} for {} lower than its minimum value {}".format(
                    result, self.key, self.min_grade
                )
                raise ValueError(msg)
        return result


class FileColumn(Column):
    def __init__(self, key, base_path=None, filename_template=None, content_type=None):
        self.base_path = base_path
        self.filename_template = filename_template
        self.content_type = content_type
        super().__init__(key, is_file=True)

    def as_dict(self, value):
        return {self.key: AttachmentFile(self._get_filename(value), self.content_type)}

    def _get_filename(self, value):
        if self.filename_template is None:
            filename = value
        else:
            filename = self.filename_template.format(value)
        if self.base_path is not None:
            filename = os.path.join(self.base_path, filename)
        return filename


class AttachmentFile:
    def __init__(self, filename, content_type):
        self.filename = filename
        self.content_type = content_type
        if self.content_type is not None:
            parts = self.content_type.split("/")
            self.main_type = parts[0]
            self.subtype = parts[1]
        else:
            self.main_type = "application"
            self.subtype = "octent-stream"

    def as_mime_part(self):
        part = MIMEBase(self.main_type, self.subtype)
        with open(self.filename, "rb") as f:
            part.set_payload(f.read())
        part.add_header(
            "Content-Disposition",
            'attachment; filename="{}"'.format(os.path.basename(self.filename)),
        )
        email.encoders.encode_base64(part)
        return part


class Address:
    def __init__(self, email=None, full_name=None):
        self._email = email
        self.full_name = full_name

    @property
    def email(self):
        if not self._email:
            raise ValueError("The user has no email")
        return email.utils.formataddr((self.full_name, self._email))


class Recipient(Address):
    def __init__(self, columns=None, values=None):
        self.full_name = None
        self._email = None
        self.file_columns = []
        if columns and values:
            for column, value in zip(columns, values):
                self.set_column(column, value)

    def set_column(self, column, value):
        for key, value in column.as_dict(value).items():
            if key != "email":
                setattr(self, key, value)
        if column.is_full_name:
            self.full_name = value
        elif column.is_email:
            self._email = value
        elif column.is_file:
            self.file_columns.append(column)

    def exclude(self):
        return False

    def __str__(self):
        return self.email


class Mailer:
    def __init__(
        self,
        smtp_server,
        subject,
        template_text,
        recipients,
        from_address,
        cc_addresses=None,
        cmd_args=None,
    ):
        self.smtp_server = smtp_server
        self.subject = subject
        self.template_text = template_text
        self.recipients = recipients
        self.from_address = from_address
        self.cc_addresses = cc_addresses
        self.cmd_args = cmd_args

    def process(self):
        simulate = not self.cmd_args.send_emails
        if self.cmd_args.send_to_recipients:
            alt_to_address = None
        else:
            alt_to_address = self.from_address
        if not self.cmd_args.just_print:
            self.send(
                simulate=simulate,
                print_mails=False,
                alt_to_address=alt_to_address,
                max_num_emails=self.cmd_args.max_num_emails,
                delay=self.cmd_args.delay,
            )
        else:
            self.test(max_num_emails=self.cmd_args.max_num_emails)

    def send(
        self,
        simulate=True,
        print_mails=False,
        alt_to_address=None,
        max_num_emails=0,
        delay=None,
    ):
        smtp_client = smtplib.SMTP(self.smtp_server)
        num_emails = 0
        for recipient in [r for r in self.recipients if not r.exclude()]:
            message = self._build_message(recipient, alt_to_address)
            if print_mails:
                print(message)
            if not simulate:
                smtp_client.send_message(message)
                if alt_to_address is None:
                    print("Email sent to:", recipient.email, file=sys.stderr)
                else:
                    print(
                        "Email sent to:",
                        alt_to_address.email,
                        "instead of",
                        recipient.email,
                        file=sys.stderr,
                    )
            else:
                if alt_to_address is None:
                    print(
                        "Email simulated (not sent) to:",
                        recipient.email,
                        file=sys.stderr,
                    )
                else:
                    print(
                        "Email simulated (not sent) to:",
                        alt_to_address.email,
                        "instead of",
                        recipient.email,
                        file=sys.stderr,
                    )
            num_emails += 1
            if max_num_emails and max_num_emails <= num_emails:
                break
            if delay is not None:
                time.sleep(delay)
        smtp_client.quit()

    def test(self, max_num_emails=0):
        num_emails = 0
        for recipient in [r for r in self.recipients if not r.exclude()]:
            print(self._build_test_message(recipient))
            print()
            num_emails += 1
            if max_num_emails and max_num_emails <= num_emails:
                break
        for recipient in [s for s in self.recipients if s.exclude()]:
            print("Excluded: ", recipient)

    def _build_message(self, recipient, alt_to_address):
        text_part = MIMEText(self.template_text.format(recipient))
        if len(recipient.file_columns) == 0:
            message = text_part
        else:
            message = MIMEMultipart()
            message.attach(text_part)
            for column in recipient.file_columns:
                message.attach(getattr(recipient, column.key).as_mime_part())
        message["Subject"] = self.subject
        message["From"] = self.from_address.email
        if not alt_to_address:
            message["To"] = recipient.email
            if self.cc_addresses:
                message["Cc"] = ",".join(a.email for a in self.cc_addresses)
        else:
            message["To"] = alt_to_address.email
        return message

    def _build_test_message(self, recipient):
        message = {}
        message["Recipient"] = recipient.email
        message["Attachments"] = []
        message["Body_text"] = self.template_text.format(recipient)
        if len(recipient.file_columns) == 0:
            message["Type"] = "NoMultipartMessage"
        else:
            message["Type"] = "MultipartMessage"
            for column in recipient.file_columns:
                message["Attachments"].append(getattr(recipient, column.key))
        message["Subject"] = self.subject
        message["From"] = self.from_address.email
        message["To"] = recipient.email
        if self.cc_addresses:
            message["Cc"] = ",".join(a.email for a in self.cc_addresses)
        else:
            message["Cc"] = ""
        main_text = (
            "Recipient: {}\n"
            "Format: {}\n"
            "From: {}\n"
            "To: {}\n"
            "Cc: {}\n"
            "Subject: {}\n\n"
            "{}\n"
        ).format(
            message["Recipient"],
            message["Type"],
            message["From"],
            message["To"],
            message["Cc"],
            message["Subject"],
            message["Body_text"],
        )
        attachments = "".join(
            [
                ("Attachment {0.filename} " "[{0.main_type}/{0.subtype}]").format(
                    attachment
                )
                for attachment in message["Attachments"]
            ]
        )
        return "\n".join((main_text, attachments))
