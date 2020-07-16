from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.contrib.auth.forms import AuthenticationForm
from .forms import *
from django.contrib.auth import login, logout, authenticate
from django.contrib import messages
from django.apps import apps
from django.conf import settings
from django.core.paginator import Paginator
import json
import operator
from django.db.models import Q
from .route import RouteCalc, format_to_time, format_to_km, output_result_db_to_csv, format_to_duration
import os
import copy


# #Главная
# def homepage(request):
#     #return HttpResponse("Test response")
#     return render(request=request,
#                   template_name='main/home.html',
#                   context={'AccLogs': AccessLog.objects.all()}
#                  )

#Ajax запрос списка складов с их кодами
def ajax_getStores(request):
    results = {}
    if request.is_ajax():
        def get_res_store():
            q = request.GET.get('term', '')
            if not q:
                return
            search_qs = Store.objects.filter(Q(name__icontains=q) | Q(ns_code__icontains=q))[:5]
            for r in search_qs:
                results[f"{r.ns_code} {r.name}"] = ''
            return results
        results = get_res_store()
    data = json.dumps(results)
    return HttpResponse(data, 'application/json')

#Сохранение маршрута в файл
def saveroute_request(route_set, file_format):
    if file_format != 'csv':
        return redirect("main:homepage")

    filepath = output_result_db_to_csv(route_set)
    filew = open(filepath,"rb")
    response = HttpResponse(filew.read(), content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{route_set.get_short_desc()}.csv"'
    filew.close()
    os.remove(filepath)
    return response

#Просмотр маршрута
def viewroute_request(request):
    # if not request.user.is_authenticated:
    #     return redirect("main:login")
    try:
        calc_id = int(request.GET.get('id', ''))
        gr_variant = int(request.GET.get('gr', 0))
        reis_variant = int(request.GET.get('reis', 0))
        save_request = request.GET.get('save', '')
        route_set = RouteSet.objects.get(id=calc_id)
        route_stat = RouteStat.objects.get(route_set=route_set)
    except:
        messages.error(request, "Неверная ссылка на расчет!")
        return redirect("main:homepage")

    if not route_stat.reis_count: # Пустой расчет
        return render(
            request,
            'main/message.html',
            context={'page_title': 'Пустой расчет',
                     'msg_title': 'Пустой расчет',
                     'msg_body': '<h5><p>Расчет не удался.<br>' +
                                 'Попробуйте указать менее строгие параметры расчета</p></h5>' +
                                 f'<p>{route_set}</p>',
                   })

    def in_dictlist(val, dict):
        for key, dval in dict:
            if key == val: return True
        return False

    if save_request:
        return saveroute_request(route_set, save_request)

    #список графиков для комбобокса
    route_list = Route.objects.filter(route_set=route_set)
    gr_list = []
    for graph in route_list.values_list('graph', flat=True).distinct():
        gr_list.append((graph, f"Гр. {graph}"))
    gr_list.sort(key = operator.itemgetter(0))
    if not in_dictlist(gr_variant, gr_list): gr_variant = gr_list[0][0]
    #Список рейсов для комбобокса
    reis_list = []
    for route in route_list.filter(graph=gr_variant):
        reis_list.append((route.reis, f"Рейс {route.reis}"))
    if not in_dictlist(reis_variant, reis_list): reis_variant = reis_list[0][0]

    #поиск текущего выводимого маршрута
    current_route = route_list.get(graph=gr_variant, reis=reis_variant)

    #общая статистика
    route_stat.costs = format_to_duration(route_stat.costs)

    #автомобиль
    if not current_route.dyn_auto: # Статический
        real_auto = {
            "name": current_route.get_auto().name,
            "capacity": int(current_route.get_auto().capacity),
            "used_capacity": int(current_route.get_used_capacity()),
            "driver_limit": format_to_time(current_route.get_auto().driver_limit),
            "used_driver_limit": format_to_time(current_route.get_auto().get_used_driver_limit()),
        }
    else: # Динамический
        #Поиск времени работы водителя
        first_route = Route.objects.filter(route_set=route_set).filter(graph=current_route.graph).order_by('reis')[0]
        last_route = Route.objects.filter(route_set=route_set).filter(graph=current_route.graph).order_by('-reis')[0]
        used_driver_limit = last_route.reis_start + last_route.get_all_time() - first_route.reis_start
        real_auto = {
            "name": f"Дин.авто ({current_route.graph})",
            "capacity": int(route_stat.dyn_auto_capacity),
            "used_capacity": int(current_route.get_used_capacity()),
            "driver_limit": format_to_time(route_stat.dyn_auto_driver_limit),
            "used_driver_limit": format_to_time(used_driver_limit),
        }

    #Статистика конкретного маршрута
    reis_stat = {
        "all_distance": format_to_km(current_route.get_all_distance()),
        "all_time": format_to_duration(current_route.get_all_time_with_startwait()),
        "delivery_dots_count": current_route.get_delivery_dots_count(),
    }

    #Маршрут
    route_tpl = []
    #добавление склада
    store_wait_time = current_route.reis_start - current_route.get_start_time_with_startwait() #Ожидание выезда со склада
    route_tpl.append({
        'num': 1,
        'name': f"{route_set.store.ns_code} {route_set.store.name}",
        'address': route_set.store.address,
        'distance': 0,
        'latitude': route_set.store.latitude,
        'longtitude': route_set.store.longtitude,
        'time_in': format_to_time(current_route.reis_start),
        'time_out': format_to_time(current_route.reis_start + current_route.load_time),
        'wait_time': ('' if not store_wait_time else format_to_time(store_wait_time)),
        'type': 'store'
    })
    #добавление магазинов
    delivery_dots = RouteDot.objects.filter(route=current_route).order_by('num')
    last_dot_num = 1
    last_time_out = current_route.reis_start
    last_coord = {'latitude': '', 'longtitude': ''}
    for dot in delivery_dots:
        dot_init = dot.get_init_dot()
        dot_client = dot_init.client
        if dot_client:
            client_name = f"{dot_client.ns_code} {dot_init.client_name}"
        else:
            client_name = dot_init.client_name
        client_address = dot_client.address if dot_client else ''
        dot_latitude = dot_init.latitude
        dot_longtitude = dot_init.longtitude
        if not dot_latitude or not dot_longtitude:
            dot_latitude = dot_client.latitude
            dot_longtitude = dot_client.longtitude
        if not (last_coord['latitude'] == dot_latitude and last_coord['longtitude'] == dot_longtitude):
            last_dot_num += 1 #С одинаковыми координатами считаем что точка та же самая
        route_tpl.append({
            'num': last_dot_num,
            'name': client_name,
            'address': client_address,
            'distance': format_to_km(dot.distance),
            'latitude': dot_latitude,
            'longtitude': dot_longtitude,
            'time_in': format_to_time(dot.time_in),
            'time_out': format_to_time(dot.time_out),
            'wait_time': ('' if not dot.wait_time else format_to_time(dot.wait_time)),
            'type': 'client',
        })
        last_time_out = dot.time_out
        last_coord = {'latitude': dot_latitude, 'longtitude': dot_longtitude}
    #добавление склада в конец маршрута (если необходимо)
    if route_stat.with_return:
        store_dot = copy.deepcopy(route_tpl[0])
        store_dot['num'] = 1
        store_dot['distance'] = format_to_km(current_route.store_return_distance)
        store_dot['time_in'] = format_to_time(last_time_out + current_route.store_return_time)
        store_dot['time_out'] = ''
        store_dot['wait_time'] = ''
        route_tpl.append(store_dot)

    #Нераспределенные точки
    unallocated_dots = []
    u_dots = route_set.get_unallocated_delivery_dots()
    for dot in u_dots:
        dot_client = dot.client
        if dot_client:
            client_name = f"{dot_client.ns_code} {dot.client_name}"
        else:
            client_name = dot.client_name
        client_address = dot_client.address if dot_client else ''
        unallocated_dots.append({
            'name': client_name,
            'address': client_address,
            'quantity': dot.quantity,
            'window_in': format_to_time(dot.window_in),
            'window_out': format_to_time(dot.window_out),
        })

    form = RouteForm(
        initial={
            'gr': gr_variant,
            'reis': reis_variant,
            'id': calc_id
        },
        gr_list=gr_list,
        reis_list=reis_list
    )

    return render(request,
                  'main/viewroute.html',
                  context={'form': form,
                           'gr_list': gr_list,
                           'route_set': route_set,
                           'calculate_stat': route_stat,
                           'real_auto': real_auto,
                           'reis_stat': reis_stat,
                           'route': route_tpl,
                           'calc_id': calc_id,
                           'unallocated_dots': unallocated_dots,
                           })


#Новый расчет
def calcnew_request(request):
    if not request.user.is_authenticated:
        return redirect("main:login")

    if request.method == "POST":
        form = CalcNewForm(request.POST, request.FILES)
        if form.is_valid():
            print(form.cleaned_data.get('store'))
            if form.cleaned_data.get('auto_list') is not None:
                print(f"{len(form.cleaned_data.get('auto_list'))} {form.cleaned_data.get('auto_list')}")
            else:
                print("No static auto")
            print(f"{len(form.cleaned_data.get('clients_list'))} {form.cleaned_data.get('clients_list')}")
            print(form.cleaned_data.get('dyn_auto_count_max'))
            print(form.cleaned_data.get('dyn_auto_capacity'))
            print(form.cleaned_data.get('dyn_auto_reis_max'))
            print(form.cleaned_data.get('dyn_auto_driver_limit'))
            try:
                current_calc = RouteCalc(
                    request=request,
                    store_object=form.cleaned_data.get('store'),
                    auto_list=form.cleaned_data.get('auto_list'),
                    delivery_dots_list=form.cleaned_data.get('clients_list'),
                    dyn_auto={
                        "count_max": form.cleaned_data.get('dyn_auto_count_max'),
                        "capacity": form.cleaned_data.get('dyn_auto_capacity'),
                        "reis_max": form.cleaned_data.get('dyn_auto_reis_max'),
                        "driver_limit": form.cleaned_data.get('dyn_auto_driver_limit'),
                    },
                    params={
                        "with_return": form.cleaned_data.get('with_return'),
                        "high_accuracy": form.cleaned_data.get('high_accuracy'),
                        "auto_min": form.cleaned_data.get('auto_min'),
                        "early_arrival": form.cleaned_data.get('early_arrival'),
                        "lately_arrival": form.cleaned_data.get('lately_arrival'),
                    }
                )
                calc_id = current_calc.calculate_and_save()
                response = redirect('main:viewroute')
                response['Location'] += f"?id={calc_id}"
                return response
            except ValueError as e:
                if settings.DEBUG:
                    raise
                messages.error(request, f"Ошибка расчета: {str(e)}")
        else:
            messages.error(request, f"Ошибка загрузки!")
    else:
        form = CalcNewForm
    return render(request,
                  'main/calcnew.html',
                  context={'form': form}
                 )


#История расчетов
def calclist_request(request):
    if not request.user.is_authenticated:
        return redirect("main:login")

    filter_user = request.GET.get('filter_user', '')
    if not any(filter_user == single_choice[0] for single_choice in CALCLIST_USERFILTER_CHOICES):
        filter_user = CALCLIST_USERFILTER_CHOICES[0][0]

    form = CalcListForm(initial={'filter_user': filter_user})

    if filter_user == 'all':
        route_sets = RouteSet.objects.all().order_by('-id')
    else:
        route_sets = RouteSet.objects.filter(username=request.user).order_by('-id')

    paginator = Paginator(route_sets, 10, allow_empty_first_page=True)
    page = request.GET.get('page')
    route_sets = paginator.get_page(page)

    return render(
        request=request,
        template_name='main/calclist.html',
        context={
            'route_sets': route_sets,
            'form': form,
        }
    )


#Импорт из excel в бд
def import_request(request):
    if not request.user.is_authenticated:
        return redirect("main:login")

    if request.method == "POST":
        form = ImportFileForm(request.POST,
                              request.FILES)
        if form.is_valid():
            map_dicts = {
                'Client': ["ns_code", "name", "latitude", "longtitude", "address",],
                'Store': ["ns_code", "name", "latitude", "longtitude", "address",],
            }

            import_table = form.cleaned_data.get('table')
            if import_table not in map_dicts:
                messages.error(request, f"Загрузка таблицы не предусмотрена!")
                return redirect("main:import")

            #проверка доступа
            if not request.user.is_staff:
                if import_table != 'Client':
                    messages.error(request, f"Вам разрешена загрузка только контрагентов!")
                    return redirect("main:import")
                if form.cleaned_data.get('rewrite'):
                    messages.error(request, f"Вам разрешена только загрузка без перезаписи!")
                    return redirect("main:import")

            try:
                import_model = apps.get_model('main', import_table)
                def filter_func(rows):
                    rows = list(rows)
                    #Проверка на первую колонку (в ней пишется тип того, что импортируем)
                    if rows[0].replace('\t', '').lower() != import_table.lower():
                        raise ValueError('Неправильный тип файла (проблема с 1 колонкой)')
                    else:
                        del rows[0]

                    #Проверка на пустые координаты
                    if not rows[2] or not rows[3]:
                        messages.error(request, f'Обьект не был загружен из-за пустых координат: {rows[0]} {rows[1]}')
                        return

                    # Переписывать ли имеющиеся строки
                    if form.cleaned_data.get('rewrite'):
                        import_model.objects.filter(ns_code=rows[0]).delete()
                    else:
                        try: #Если запись найдена - убираем строку из импорта
                            import_model.objects.get(ns_code=rows[0])
                            return
                        except:
                            pass
                    for idx, row in enumerate(rows):
                        # Фильтр названий
                        rows[idx] = filter_string(rows[idx])
                    return rows
                request.FILES['file'].save_to_database(
                   start_row=1,
                   #name_columns_by_row=2,
                   bulk_size=256,
                   initializer=filter_func,
                   model=import_model,
                   mapdict=map_dicts[import_table]
                )
                messages.success(request, f"Импорт успешен!")
                response = redirect('main:map')
                response['Location'] += '?table=' + import_table.lower()
                return response
            except:
                if settings.DEBUG:
                    raise
                messages.error(request, f"Ошибка: Неверный формат файла!")
                return redirect("main:import")
        else:
            messages.error(request, f"Ошибка загрузки!")
            return redirect("main:import")

    form = ImportFileForm
    return render(request,
                  'main/import.html',
                  context={'form': form}
                 )


def map_request(request):
    #Какие объекты необходимо отображать на карте
    map_variant = request.GET.get('table', '').capitalize()
    if not any(map_variant == single_choice[0] for single_choice in TABLE_CHOICES):
        map_variant = TABLE_CHOICES[0][0]

    points = apps.get_model('main', map_variant).objects.filter(latitude__gt=0).filter(longtitude__gt=0)
    form = MapForm(initial={'table': map_variant})

    return render(request,
                  'main/map.html',
                  {'form': form,
                   'points': points,
                   'map_variant': map_variant.lower(),
                   })


# def register(request):
#     if request.method == "POST":
#         form = NewUserForm(request.POST)
#         if form.is_valid():
#             user = form.save()
#             username = form.cleaned_data.get("username")
#             messages.success(request, f"Пользователь успешно зарегистрирован: {username}")
#             login(request, user)
#             messages.info(request, f"Вход под пользователем {username}")
#             return redirect("main:homepage")
#         else:
#             for msg in form.error_messages:
#                 messages.error(request, f"Ошибка {msg}:{form.error_messages[msg]}")
#
#     form = NewUserForm
#     return render(request,
#                   'main/register.html',
#                   context={'form': form}
#                  )


def logout_request(request):
    logout(request)
    messages.info(request, "Выход из учетной записи: успешно")
    return redirect("main:homepage")


def login_request(request):
    if request.method == "POST":
        form = AuthenticationForm(request, request.POST)
        if form.is_valid():
            username = form.cleaned_data.get("username")
            password = form.cleaned_data.get("password")
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                messages.info(request, f"Вход под пользователем {username}")
                return redirect("main:homepage")
        messages.error(request, 'Неверно введен логин или пароль')

    form = AuthenticationForm
    return render(request,
                  'main/login.html',
                  context={'form': form}
                 )


