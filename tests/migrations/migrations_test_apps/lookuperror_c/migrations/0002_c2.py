# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('lookuperror_a', '0002_a2'),
        ('lookuperror_c', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='C2',
            fields=[
                ('id', models.AutoField(auto_created=True, verbose_name='ID', primary_key=True, serialize=False)),
                ('a1', models.ForeignKey(to='lookuperror_a.A1')),
            ],
        ),
    ]
