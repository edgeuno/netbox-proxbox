# Generated by Django 3.2.12 on 2022-07-26 19:08

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('netbox_proxbox', '0014_auto_20220726_1847'),
    ]

    operations = [
        migrations.AlterField(
            model_name='synctask',
            name='proxmox_vm',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='netbox_proxbox.proxmoxvm'),
        ),
    ]
