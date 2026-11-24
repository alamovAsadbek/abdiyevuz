from django.urls import path

from . import views as v
from . import views_groups as g

urlpatterns = [
    path("login/", v.login_view, name="login"),
    path("register/", v.register_view, name="register"),
    path("logout/", v.logout_view, name="logout"),
    path("auth/ping/", v.ping, name="ping"),
    path("profile/", v.profile, name="profile"),
    path("settings/", v.settings_view, name="settings"),
    path("dashboard/", g.dashboard, name="dashboard"),
    path("stats/", g.stats, name="stats"),
    path("staff/users/", v.users, name="users"),
    path("staff/users/new/", v.user_new, name="user_new"),
    path("staff/users/bulk/", v.user_bulk, name="user_bulk"),
    path("staff/users/<int:pk>/", v.user_detail, name="user_detail"),
    path("staff/users/<int:pk>/edit/", v.user_edit, name="user_edit"),
    path("staff/users/<int:pk>/block/", v.user_block, name="user_block"),
    path("staff/users/<int:pk>/delete/", v.user_delete, name="user_delete"),
    path("staff/users/<int:pk>/perm/", v.user_perm, name="user_perm"),
    path("settings/roles/<str:role>/", v.role_perms, name="role_perms"),
    path("staff/users/<int:pk>/groups/", g.user_groups, name="user_groups"),
    path("groups/", g.groups, name="groups"),
    path("groups/new/", g.group_new, name="group_new"),
    path("groups/<int:pk>/", g.group_detail, name="group_detail"),
    path("groups/<int:pk>/edit/", g.group_edit, name="group_edit"),
    path("groups/<int:pk>/toggle/", g.group_toggle, name="group_toggle"),
    path("groups/<int:pk>/delete/", g.group_delete, name="group_delete"),
    path("groups/<int:pk>/members/", g.group_members, name="group_members"),
    path("groups/<int:pk>/assistants/", g.group_assistants, name="group_assistants"),
]
