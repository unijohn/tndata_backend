This endpoint represents a user's selected Actions. That is, an object that
defines a mapping between [Users](/api/users/) and [Actions](/api/actions/).

GET requests to this page will simply list this `UserAction` objects belonging
to the authenticated user.

## Fields

This endpoint returns resources with the following fields.

* `id`: A unique identifier for the `UserAction`
* `user`: A unique identifier for the `User`
* `action`: An object that represents the `Action` selected by the user
* `next_reminder`: a date/time in the user's local timezone for the
  next push notification for this action (may be null if nothing is scheduled)
* `custom_trigger`: An object that represent's the user's created `Trigger`,
  i.e. information about when notifications for this action should be sent. It
  will contain the following additional data:

      - `id`: Unique ID of the Trigger
      - `name`: The trigger's name
      - `trigger_date`: Date on which the trigger shoudl start
      - `time`: Time at which the trigger should fire
      - `recurrences`: an RFC 2445 RRULE string (or null)
      - `recurrences_display`: a human-readable version of recurrences

* `editable`: A boolean that indicates whether or not a user
  should be able to customize the reminders for this action.
* `primary_goal`: The ID of the goal under which the user selected this action.
* `primary_category`: The ID of the category associated with this action.
* `created_on`: Time at which the user selected this item.
* `object_type`: A string that will always be `useraction`

## Adding a UserAction

To associate a Action with a User, POST to `/api/users/actions/` with the
following data (the action the user is selecting, and (optionally) the
parent goal and category for the action).

    {
        'action': ACTION_ID,
        'primary_goal': GOAL_ID,         # (optional)
        'primary_category': CATEGORY_ID  # (optional)
    }

## Adding a UserAction and all parent objects at once

If you submit a `category`, `goal`, `behavior`, and `action` all in a single
payload, each object will be added to the user's collection at once; This will
simplify adding the tree of data. When using this payload, all items are required,
and the given `goal` and `category` IDs will be set as the `primary_goal` and
`primary_category`:

    {
        'action': ACTION_ID,
        'behavior': BEHAVIOR_ID,
        'goal': GOAL_ID,
        'category': CATEGORY_ID
    }

When POSTing the above information to `/api/users/actions/`, the returned result
will also include additional information about these parent objects as
`parent_usercategory`, `parent_usergoal`, and `parent_userbehavior` items within
the `useraction` details.  For example, the result JSON, would be similar to
the following:

    {
      "id": 5406,
      "user": 1,
      "action": {...},
      "trigger": {...},
      "next_reminder": null,
      "editable": true,
      "created_on": "2016-01-21T17:45:19.725448Z",
      "primary_goal": 20,
      "primary_category": 24,
      "object_type": "useraction",
      "parent_catgory": {
        "id": 1160,
        "user": 1,
        "category": {...},
        "created_on": "2016-01-20T23:21:16.153161Z",
        "editable": true,
        "object_type": "usercategory"
      },
      "parent_goal": {
        "id": 1908,
        "user": 1,
        "goal": {...},
        "editable": true,
        "created_on": "2016-01-21T17:33:19.223719Z",
        "primary_category": 24,
        "object_type": "usergoal"
      },
      "parent_behavior": {
        "id": 1962,
        "user": 1,
        "behavior": {...},
        "created_on": "2016-01-21T17:33:19.319116Z",
        "editable": true,
        "object_type": "userbehavior"
      }
    }


## Viewing UserActions

Additional information for the UserAction is available at
`/api/users/actions/{useraction_id}/`. In this case, `{useraction_id}`
is the database id for the mapping between a user and a action.

## Deleting a UserAction

Send a DELETE request to the useraction endpoint:
`/api/users/actions/{useraction_id}/`.

## Update a UserAction / Custom Triggers

UserActions may be updated in order to set custom Triggers (aka
reminders) for the associated action.

To do this, send a PUT request to the detail url
(`api/users/actions/{useraction_id}`) with the following information:

* `custom_trigger_time`: The time at which the reminder should fire, in
  `hh:mm` format, in the user's local time.
* `custom_trigger_date`: (optional). For a one-time reminder, this can
  include a date string (yyyy-mm-dd) to define the date at which a reminder
  should next fire. The date should be relative to the user's local time.
* `custom_trigger_rrule`: A Unicode RFC 2445 string representing the days &amp;
  frequencies at which the reminder should occur.

## Filtering

UserActions can be filtered using a query string parameter. Currently,
filtering is availble for Goals, Behaviors, Actions, and for Actions
whose notification is scheduled during the current day.

To filter for actions scheduled _today_, use the following:

* `/api/users/actions/?today=1`

For the following examples, you may filter using an ID or a slug.

To retrieve all UserActions that belong to a particular Goal, use
one of the following:

* `/api/users/actions/?goal={goal_id}` or by slug
* `/api/users/actions/?goal={goal_title_slug}`

To retrieve all UserActions that belong to a particular Behavior, use
one of the following:

* `/api/users/actions/?behavior={behavior_id}` or by slug
* `/api/users/actions/?behavior={behavior_title_slug}`

To retrive all UserActionss that belong to a particular Action, use one
of the following:

* `/api/users/actions/?action={action_id}` or by slug
* `/api/users/actions/?action={action_title_slug}`

**NOTE**: Action titles are not unique, so filtering by the `title_slug`
may return a number of results.

## Additional information

The Actions that a User has selected are also available through the
`/api/users/` endpoint as a `actions` object on the user.

## Completing Actions (or not)

A User may wish to indicate that they have performed (or completed),
dismissed, snoozed, or have decided not to complete an action. To save this
information:

* send a POST request to `/api/users/actions/{useraction_id}/complete/`
  with a body containing a `state` and an optional `length`; these values
  tell us how the user responded to the action, and how long they snoozed
  the action (if that's what they did).

        {
            'state': 'snoozed', # or 'completed', 'uncompleted', 'dismissed'
            'length': '1hr'     # or  "1d", "custom", "location"
        }

* A 200 response indicates that the action has been updated or created. If
  updated, the response will be: `{updated: <object_id>}`, if created:
  `{created: <object_id>}`.

----
