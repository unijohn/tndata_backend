# -*- coding: utf-8 -*-
# Generated by Django 1.9.9 on 2016-09-21 19:37
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('goals', '0171_auto_20160913_1649'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='usergoal',
            name='serialized_goal',
        ),
        migrations.RemoveField(
            model_name='usergoal',
            name='serialized_goal_progress',
        ),
        migrations.RemoveField(
            model_name='usergoal',
            name='serialized_primary_category',
        ),
        migrations.RemoveField(
            model_name='usergoal',
            name='serialized_user_behaviors',
        ),
        migrations.RemoveField(
            model_name='usergoal',
            name='serialized_user_categories',
        ),
    ]
