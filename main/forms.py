from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import *
import datetime

TABLE_CHOICES = [
    ('Store', 'Склады'),
    ('Client', 'Клиенты'),
]

CALCLIST_USERFILTER_CHOICES = [
    ('personal','Показать личные'),
    ('all','Показать все')
]

def filter_time(val, val_type_name, val_name, row_index): #фильтрация времени (пришедшего из excel)
    if isinstance(val, datetime.datetime):
        val = f"{val.hour}:{val.minute}"  # из datetime вытаскиваем time
    val = filter_string(str(val).split(':'))
    try:
        if len(val) < 2 or int(val[0]) < 0 or int(val[0]) > 23 or int(val[1]) < 0 or int(val[1]) > 60:
            raise forms.ValidationError(f"{val_type_name}: строка {row_index} - неверно указано поле: {val_name}")
    except:
        raise forms.ValidationError(f"{val_type_name}: строка {row_index} - неверно указано поле: {val_name}")
    return val

def filter_digit(val, type, val_type_name, val_name, row_index, min_val=None, max_val=None, min_val_include = False, max_val_include = False): #фильтрация чисел (пришедших из excel)
    try:
        val = type(filter_string(str(val)))
    except:
        raise forms.ValidationError(f"{val_type_name}: строка {row_index} - неверно указано поле: {val_name}")
    if min_val is not None:
        val_more_key = '>'
        if min_val_include: val_more_key = '>='
        if (min_val_include and val < min_val) or (not min_val_include and val <= min_val):
            raise forms.ValidationError(f"{val_type_name}: строка {row_index} - поле {val_name} должно быть {val_more_key} {min_val}")
    if max_val is not None:
        val_less_key = '<'
        if max_val_include: val_less_key = '<='
        if (max_val_include and val > max_val) or (not max_val_include and val >= max_val):
            raise forms.ValidationError(f"{val_type_name}: строка {row_index} - поле {val_name} должно быть {val_less_key} {max_val}")
    return val

def filter_string(val): #фильтрация строк (из excel)
    if isinstance(val, str):
        val = val.replace('\t', ' ').strip()
    return val


# class NewUserForm(UserCreationForm):
#     email = forms.EmailField(required=True)
#
#     class Meta:
#         model = User
#         fields = ("username", "email", "password1", "password2")
#
#         def save(self, commit=True):
#             user = super(NewUserForm, self).save(commit=False)
#             user.email = self.cleaned_data['email']
#             if commit:
#                 user.save()
#             return user

class ImportFileForm(forms.Form):
    table = forms.ChoiceField(choices=TABLE_CHOICES, label="База для импорта", widget=forms.Select(), required=True)
    rewrite = forms.BooleanField(label="Перезаписывать имеющиеся?", widget=forms.CheckboxInput(), required=False)
    file = forms.FileField(label="Excel файл", required=True)

class MapForm(forms.Form):
    table = forms.ChoiceField(choices=TABLE_CHOICES, label="Объект",
                              widget=forms.Select(attrs={'onchange': 'mapform.submit();'}))

class RouteForm(forms.Form):
    def __init__(self, *args, **kwargs):
        self.gr_list = kwargs.pop('gr_list')
        self.reis_list = kwargs.pop('reis_list')
        super(RouteForm, self).__init__(*args, **kwargs)
        self.fields['gr'] = forms.ChoiceField(choices=self.gr_list, label="",
                                widget=forms.Select(attrs={'onchange': 'document.getElementById("id_reis").value = 1;routeform.submit();'}))
        self.fields['reis'] = forms.ChoiceField(choices=self.reis_list, label="",
                                widget=forms.Select(attrs={'onchange': 'routeform.submit();'}))

    id = forms.IntegerField()

class CalcListForm(forms.Form):
    filter_user = forms.ChoiceField(choices=CALCLIST_USERFILTER_CHOICES, label="Фильтр",
                              widget=forms.Select(attrs={'onchange': 'calclistform.submit();'}))

class CalcNewForm(forms.Form):
    store = forms.CharField(label="Склад", widget=forms.TextInput(attrs={'class':'autocomplete',
                                                                         'title': 'Начните вводить код или название склада NS2000'}),
                            required=True)
    with_return = forms.BooleanField(label="C возвратом на склад", widget=forms.CheckboxInput(), required=False,
                                     initial=True)
    high_accuracy = forms.BooleanField(label="Полный расчет", widget=forms.CheckboxInput(), required=False,
                                     initial=False)
    auto_min = forms.BooleanField(label="Минимизация кол-ва авто", widget=forms.CheckboxInput(), required=False,
                                     initial=True)
    #Нестрогие окна доставки
    early_arrival = forms.IntegerField(label="раньше на (мин.)", required=True, min_value=0, initial=5)
    lately_arrival = forms.IntegerField(label="позже на (мин.)", required=True, min_value=0, initial=5)
    #Динамические авто
    dyn_auto_count_max = forms.IntegerField(label="Кол-во(макс.)", required=True, min_value=0, max_value=99, initial=0)
    dyn_auto_capacity = forms.IntegerField(label="Емкость", required=True, min_value=1, initial=160)
    dyn_auto_reis_max = forms.IntegerField(label="Рейсов(макс.)", required=True, min_value=1, max_value=9, initial=3)
    dyn_auto_driver_limit = forms.DateTimeField(label="Смена", required=True, input_formats=['%H:%M'],
                                                widget=forms.DateTimeInput(format='%H:%M'),
                                                initial=datetime.datetime.utcfromtimestamp(0).replace(hour=11, minute=00))
    #Файлы excel
    auto_list = forms.FileField(label="Файл с Авто(Excel)", required=False)
    clients_list = forms.FileField(label="Файл с ТТ(Excel)", required=True)

    def clean_lately_arrival(self): #Проверка времени позднего прибытия и привод к единому времени системы (в секундах)
        try:
            lately_arrival = int(self.cleaned_data['lately_arrival'])
        except:
            raise forms.ValidationError("Неверное число минут позднего прибытия")
        if lately_arrival < 0:
            raise forms.ValidationError("Неверное число минут позднего прибытия")
        return lately_arrival * 60

    def clean_early_arrival(self): #Проверка времени раннего прибытия и привод к единому времени системы (в секундах)
        try:
            early_arrival = int(self.cleaned_data['early_arrival'])
        except:
            raise forms.ValidationError("Неверное число минут раннего прибытия")
        if early_arrival < 0:
            raise forms.ValidationError("Неверное число минут раннего прибытия")
        return early_arrival * 60

    def clean_store(self): #Проверяем на корректность и возвращаем обьект - склад (вместо его названия)
        store = self.cleaned_data['store'].split(" ")[0]
        try:
            store = Store.objects.get(ns_code=int(store))
        except:
            raise forms.ValidationError("Неверный выбор склада")
        return store

    def clean_dyn_auto_driver_limit(self): #Возврат кол-во часов смены водителя в секундах
        dyn_auto_driver_limit = self.cleaned_data['dyn_auto_driver_limit']
        dyn_auto_driver_limit = dyn_auto_driver_limit.hour * 60 * 60 + dyn_auto_driver_limit.minute * 60
        if not dyn_auto_driver_limit > 0:
            raise  forms.ValidationError("Слишком короткая смена водителя")
        return dyn_auto_driver_limit

    def clean_auto_list(self):
        if self.cleaned_data['auto_list'] is None:
            return []
        try:
            sheet = self.cleaned_data.get('auto_list').get_sheet(start_row=2)
        except:
            raise forms.ValidationError(f"Авто: Ошибка в excel файле (возможно поле времени)")
        auto_list = []
        for idx, row in enumerate(sheet): #Перебор строк excel
            row_index = idx + 3
            if len(row) < 5:
                raise forms.ValidationError(f"Авто: строка {row_index} - не хватает данных в столбце")
            #Госномер
            row[0] = filter_string(row[0])
            if not row[0]:
                raise forms.ValidationError(f"Авто: строка {row_index} - укажите госномер авто")
            #Емкость
            row[1] = filter_digit(val=row[1], type=int, val_type_name="Авто", val_name="емкость", row_index=row_index,
                                  min_val=0, min_val_include=False)
            #Макс.Рейсов
            row[2] = filter_digit(val=row[2], type=int, val_type_name="Авто", val_name="кол-во рейсов", row_index=row_index,
                                  min_val=0, min_val_include=False)
            #Время выезда
            start_time_free = False #Время принудительно не было указано (свободное время старта)
            if not row[3]:
                start_time = 0
                start_time_free = True
            else:
                row[3] = filter_time(val=row[3], val_type_name="Авто", val_name="время выезда", row_index=row_index)
                start_time = int(row[3][0]) * 60 * 60 + int(row[3][1]) * 60
                if not start_time > 20 * 60 * 60: #Если время приезда на погрузку указано с 20:00 и далее, считаем, что день предыдущий
                    start_time += 86400 # Иначе - ко времени прибавляем +1 сутки для отображения текущего дня
            #Ограничение времени работы водителя (смена)
            if not row[4]:
                row[4] = '23:59'
            row[4] = filter_time(val=row[4], val_type_name="Авто", val_name="время работы водителя", row_index=row_index)
            if (int(row[4][0]) == 0 and int(row[4][1]) == 0):
                row[4][0] = 23
                row[4][1] = 59
            driver_limit = int(row[4][0]) * 60 * 60 + int(row[4][1]) * 60

            #Запись результата
            auto_list.append({
                'name': row[0],
                'capacity': row[1],
                'reis_max': row[2],
                'start_time': start_time,
                'start_time_free': start_time_free,
                'driver_limit': driver_limit,
            })
        if len(auto_list) == 0:
            raise forms.ValidationError(f"Авто: файл пуст")
        return auto_list

    def clean_clients_list(self):
        try:
            sheet = self.cleaned_data.get('clients_list').get_sheet(start_row=2)
        except:
            raise forms.ValidationError(f"ТТ: Ошибка в excel файле (возможно неверное окно доставки)")
        clients_list = []
        for idx, row in enumerate(sheet):  # Перебор строк excel
            row_index = idx + 3
            if len(row) < 7:
                raise forms.ValidationError(f"ТТ: строка {row_index} - не хватает данных в столбце")
            #Поиск магазина в базе по коду
            try:
                row[1] = Client.objects.get(ns_code=int(row[1]))
            except:
                #raise forms.ValidationError(f"ТТ: строка {row_index} - неверно указан код магазина (не найден в базе)")
                row[1] = None
            #Название
            row[0] = filter_string(row[0])
            if not row[0]:
                if not row[1]:
                    raise forms.ValidationError(f"ТТ: строка {row_index} - не найден в базе и нет названия магазина!")
                row[0] = row[1].name
            #Кол-во заказанных лотков
            row[2] = filter_digit(val=row[2], type=float, val_type_name="ТТ", val_name="кол-во заказанных лотков", row_index=row_index,
                                  min_val=0, min_val_include=True)
            # Приоритет
            row[3] = filter_digit(val=row[3], type=int, val_type_name="ТТ", val_name="приоритет", row_index=row_index,
                                  min_val=0, min_val_include=True, max_val=10, max_val_include=True)
            #Окно доставки С
            row[4] = filter_time(val=row[4], val_type_name="ТТ", val_name="окно доставки с", row_index=row_index)
            window_from = int(row[4][0]) * 60 * 60 + int(row[4][1]) * 60
            if window_from > 0:
                window_from += 86400 # Прибавляем ко времени +1 сутки (станет вместо предыдущего дня - текущий)
            #Окно доставки По
            row[5] = filter_time(val=row[5], val_type_name="ТТ", val_name="окно доставки по", row_index=row_index)
            window_to = int(row[5][0]) * 60 * 60 + int(row[5][1]) * 60
            if window_to > 0:
                window_to += 86400 # Прибавляем ко времени +1 сутки (станет вместо предыдущего дня - текущий)
            if window_to > 0 and window_from > window_to:
                raise forms.ValidationError(f"ТТ: строка {row_index} - неверно указаны окна доставки")
            #Время разгрузки в минутах
            row[6] = filter_digit(val=row[6], type=int, val_type_name="ТТ", val_name="время разгрузки", row_index=row_index,
                                  min_val=0, min_val_include=True)
            #Широта и долгота
            try:
                latitude = filter_digit(val=row[7], type=float, val_type_name="ТТ", val_name="",
                                      row_index=row_index, min_val=0, min_val_include=False)
                longtitude = filter_digit(val=row[8], type=float, val_type_name="ТТ", val_name="",
                                      row_index=row_index, min_val=0, min_val_include=False)
            except:
                if not row[1]:
                    raise forms.ValidationError(f"ТТ: строка {row_index} - не найден в базе и нет координат!")
                latitude = row[1].latitude
                longtitude = row[1].longtitude
            # Адрес тт (в случае, если тт есть в базе - не пишем)
            if row[1]:
                row[9] = None

            #Запись результата
            clients_list.append({
                'client_name': row[0],
                'client_object': row[1],
                'quantity': row[2],
                'priority': row[3],
                'window_from': window_from,
                'window_to': window_to,
                'process_time': row[6] * 60,
                'latitude': latitude,
                'longtitude': longtitude,
                'client_address': row[9],
            })
        if len(clients_list) == 0:
            raise forms.ValidationError(f"ТТ: файл пуст")
        return clients_list
