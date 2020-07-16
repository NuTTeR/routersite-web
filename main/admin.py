from django.contrib import admin
from .models import *
from tinymce.widgets import TinyMCE
from django.db import models

# Register your models here.
# class AccessLogAdmin(admin.ModelAdmin):
#     # fields = ["host_ip",
#     #           "access_date",
#     #          ]
#
#     fieldsets = [
#         ("Userdata", {"fields" : ["host_ip", "host_useragent"]}),
#         ("Serverdata", {"fields" : ["host_url", "access_date"]}),
#         ("Admin area", {"fields" : ["log_comment"]}),
#     ]
#
#     formfield_overrides = {
#         models.TextField: {'widget': TinyMCE()}
#     }
#
# class NewsAdmin(admin.ModelAdmin):
#     formfield_overrides = {
#         models.TextField: {'widget': TinyMCE()}
#     }
#
# admin.site.register(AccessLog, AccessLogAdmin)
# admin.site.register(CategoryNews)
# admin.site.register(News, NewsAdmin)
admin.site.register(Store)
admin.site.register(Client)
admin.site.register(RouteSet)