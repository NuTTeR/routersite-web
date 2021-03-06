# Generated by Django 2.2.4 on 2020-02-17 16:18

from django.db import migrations, models
import django.db.models.deletion

def forwards_func(apps, schema_editor):
    # We get the model from the versioned app registry;
    # if we directly import it, it'll be the wrong version
    RouteSet = apps.get_model("main", "RouteSet")
    Route = apps.get_model("main", "Route")
    db_alias = schema_editor.connection.alias
    rs = RouteSet.objects.using(db_alias).all()
    for r_set in rs:
        try:
            r = Route.objects.using(db_alias).filter(route_set=r_set)[:1][0]
            r_set.store = r.store
            r_set.save(update_fields=['store'])
        except:
            pass

def reverse_func(apps, schema_editor):
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('main', '0011_auto_20191101_1628'),
    ]

    operations = [
        migrations.AddField(
            model_name='routeset',
            name='store',
            field=models.ForeignKey(default=18, on_delete=django.db.models.deletion.CASCADE, to='main.Store',
                                    verbose_name='Склад'),
        ),
        migrations.RunPython(forwards_func, reverse_func),
        migrations.RemoveField(
            model_name='route',
            name='store',
        ),
    ]
