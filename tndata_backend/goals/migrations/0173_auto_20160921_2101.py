# -*- coding: utf-8 -*-
# Generated by Django 1.9.9 on 2016-09-21 21:01
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('goals', '0172_auto_20160921_1937'),
    ]

    operations = [
        migrations.AddField(
            model_name='usergoal',
            name='engagement_15_days',
            field=models.FloatField(blank=True, default=0),
        ),
        migrations.AddField(
            model_name='usergoal',
            name='engagement_30_days',
            field=models.FloatField(blank=True, default=0),
        ),
        migrations.AddField(
            model_name='usergoal',
            name='engagement_60_days',
            field=models.FloatField(blank=True, default=0),
        ),
    ]
