# Generated by Django 3.2.12 on 2022-07-22 15:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('netbox_proxbox', '0009_auto_20220706_2033'),
    ]

    operations = [
        migrations.AddField(
            model_name='proxmoxvm',
            name='domain',
            field=models.CharField(blank=True, max_length=512, null=True),
        ),
        migrations.AddField(
            model_name='proxmoxvm',
            name='latest_job',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='proxmoxvm',
            name='latest_update',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='proxmoxvm',
            name='url',
            field=models.CharField(blank=True, max_length=512, null=True),
        ),
    ]
