# Generated by Django 2.2.4 on 2019-11-01 16:12

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0009_routestat_auto_min'),
    ]

    operations = [
        migrations.AddField(
            model_name='routeinitdot',
            name='latitude',
            field=models.FloatField(default=None, null=True, verbose_name='Широта ТТ'),
        ),
        migrations.AddField(
            model_name='routeinitdot',
            name='longtitude',
            field=models.FloatField(default=None, null=True, verbose_name='Долгота ТТ'),
        ),
    ]
