# Generated by Django 2.2.3 on 2019-07-24 10:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='routestat',
            name='early_arrival',
            field=models.PositiveIntegerField(default=15, verbose_name='На сколько можно приехать раньше окна доставки магазина (кроме приоритетных магазинов)'),
        ),
        migrations.AddField(
            model_name='routestat',
            name='lately_arrival',
            field=models.PositiveIntegerField(default=15, verbose_name='На сколько можно приехать позже окна доставки магазина (кроме приоритетных магазинов)'),
        ),
    ]