# -*- coding: utf-8 -*-
# Generated by Django 1.9.9 on 2016-09-13 16:49
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('goals', '0170_auto_20160913_1553'),
    ]

    operations = [
        migrations.AlterField(
            model_name='action',
            name='action_type',
            field=models.CharField(choices=[('showing', 'Showing'), ('resource', 'Resource Notification')], db_index=True, default='showing', max_length=32),
        ),
    ]
