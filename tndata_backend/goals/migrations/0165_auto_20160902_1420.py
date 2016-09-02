# -*- coding: utf-8 -*-
# Generated by Django 1.9.9 on 2016-09-02 14:20
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('goals', '0164_auto_20160829_2145'),
    ]

    operations = [
        migrations.AddField(
            model_name='customaction',
            name='goal',
            field=models.ForeignKey(blank=True, help_text='The goal to which this custom action is associated.', null=True, on_delete=django.db.models.deletion.CASCADE, to='goals.Goal'),
        ),
        migrations.AlterField(
            model_name='customaction',
            name='customgoal',
            field=models.ForeignKey(blank=True, help_text='The custom goal to which this action belongs.', null=True, on_delete=django.db.models.deletion.CASCADE, to='goals.CustomGoal'),
        ),
    ]
