# Generated by Django 2.2.4 on 2019-09-25 10:23

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0007_auto_20190924_1632'),
    ]

    operations = [
        migrations.AddField(
            model_name='route',
            name='dyn_auto',
            field=models.BooleanField(default=False, verbose_name='Использовалось динамическое авто'),
        ),
    ]
